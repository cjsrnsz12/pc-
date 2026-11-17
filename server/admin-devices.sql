-- REVIEW COPY ONLY. Upload and hosted deployment are paused by the owner.
begin;
alter table nyacro_players.players add column if not exists device_type text;
alter table nyacro_players.players add column if not exists used_devices smallint;
update nyacro_players.players set device_type=case when platform='pc' then 'pc' else 'mobile' end where device_type is null;
update nyacro_players.players set used_devices=case when platform='pc' then 1 else 2 end where used_devices is null;
alter table nyacro_players.players alter column device_type set not null;
alter table nyacro_players.players alter column used_devices set not null;
do $$begin
 if not exists(select 1 from pg_constraint where conname='nyacro_player_device_kind') then
  alter table nyacro_players.players add constraint nyacro_player_device_kind check(device_type in ('pc','mobile','tablet'));
  alter table nyacro_players.players add constraint nyacro_player_used_devices check(used_devices between 1 and 7);
 end if;
end$$;
-- Defaults keep inserts from the preserved v2 dispatcher working.
alter table nyacro_players.players alter column device_type set default 'mobile';
alter table nyacro_players.players alter column used_devices set default 2;

-- Per-installation high-water marks survive presence expiry. Nickname grouping
-- only changes public presentation; credentials and local counters stay separate.
create table if not exists nyacro_players.completion_ledger (
 id uuid primary key,token_hash bytea not null,nickname_key text collate "C" not null,
 lifetime_completed bigint not null check(lifetime_completed between 0 and 9000000000000000)
);
create index if not exists nyacro_completion_nickname on nyacro_players.completion_ledger(nickname_key);
alter table nyacro_players.completion_ledger enable row level security;
revoke all on nyacro_players.completion_ledger from public,anon,authenticated;
grant select,insert,update on nyacro_players.completion_ledger to service_role;
insert into nyacro_players.completion_ledger(id,token_hash,nickname_key,lifetime_completed)
 select id,token_hash,normalize(btrim(nickname),NFC),lifetime_completed from nyacro_players.players
 on conflict(id) do update set nickname_key=excluded.nickname_key,
 lifetime_completed=greatest(nyacro_players.completion_ledger.lifetime_completed,excluded.lifetime_completed)
 where nyacro_players.completion_ledger.nickname_key is distinct from excluded.nickname_key
 or nyacro_players.completion_ledger.lifetime_completed<excluded.lifetime_completed;

create table if not exists nyacro_players.admin_keys (
 id smallint primary key check(id=1),key_hash bytea not null,enabled boolean not null default false
);
create table if not exists nyacro_players.error_reports (
 id uuid primary key,player_id uuid references nyacro_players.players(id) on delete set null,
 nickname text not null,platform text not null,device_type text not null,
 app_version text not null,device_model text not null,screen text not null,content text not null,
 stop_reason text not null,logs text not null,occurred_at timestamptz not null,
 received_at timestamptz not null default clock_timestamp(),read_at timestamptz
);
create index if not exists nyacro_error_received on nyacro_players.error_reports(received_at desc,id);
create index if not exists nyacro_error_unread on nyacro_players.error_reports(received_at desc,id) where read_at is null;
create index if not exists nyacro_error_player_received on nyacro_players.error_reports(player_id,received_at desc);
alter table nyacro_players.admin_keys enable row level security;
alter table nyacro_players.error_reports enable row level security;
revoke all on nyacro_players.admin_keys,nyacro_players.error_reports from public,anon,authenticated;
grant select on nyacro_players.admin_keys to service_role;
grant select,insert,update on nyacro_players.error_reports to service_role;

do $$begin
 if to_regprocedure('public.nyacro_players_dispatch_v2(jsonb,text)') is null then
  alter function public.nyacro_players_dispatch(jsonb,text) rename to nyacro_players_dispatch_v2;
 end if;
end$$;
revoke all on function public.nyacro_players_dispatch_v2(jsonb,text) from public,anon,authenticated;
grant execute on function public.nyacro_players_dispatch_v2(jsonb,text) to service_role;

create or replace function nyacro_players.scrub(value text,bound integer) returns text
language sql immutable set search_path='' as $$
 select left(regexp_replace(regexp_replace(regexp_replace(coalesce(value,''),
  '(?i)(bearer[[:space:]]+)[A-Za-z0-9._~-]+','\1[hidden]','g'),
  '(?i)(token|password|passwd|secret|admin[_-]?key|api[_-]?key)["'']?[[:space:]]*[=:][[:space:]]*["'']?[^[:space:],;"''}]+','\1=[hidden]','g'),
  '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}','[hidden email]','g'),greatest(0,bound));
$$;
revoke all on function nyacro_players.scrub(text,integer) from public,anon,authenticated;
grant execute on function nyacro_players.scrub(text,integer) to service_role;

create or replace function public.nyacro_players_dispatch(body jsonb,rate_key text) returns jsonb
language plpgsql set search_path='' set statement_timeout='5s' as $$
declare
 op text:=body->>'op';result jsonb;uid uuid;p nyacro_players.players%rowtype;
 kind text;mask integer;rows jsonb;report jsonb;rid uuid;key_hash bytea;hits integer;bucket_value bigint;
 page_value integer;total integer;only_unread boolean;received nyacro_players.error_reports%rowtype;
 ledger nyacro_players.completion_ledger%rowtype;
begin
 if coalesce(rate_key,'') !~ '^[0-9a-f]{64}$' then return jsonb_build_object('error','invalid_request');end if;
 if op in ('players_register','players_sync','players_remove') then
  if body ? 'device_type' and coalesce(body->>'device_type','') not in ('pc','mobile','tablet') then return jsonb_build_object('error','invalid_request');end if;
  if body ? 'used_devices' and (coalesce(body->>'used_devices','') !~ '^[1-7]$') then return jsonb_build_object('error','invalid_request');end if;
  if op='players_register' and coalesce(body->>'member_id','') ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' then
   select * into ledger from nyacro_players.completion_ledger where id=(body->>'member_id')::uuid;
   if found and ledger.token_hash is distinct from extensions.digest(body->>'token','sha256') then return jsonb_build_object('error','unauthorized');end if;
  end if;
  -- Legacy code inserts default mobile; device constraints are applied after it returns.
  result:=public.nyacro_players_dispatch_v2(body,rate_key);
  if result ? 'error' or op='players_remove' then return result;end if;
  uid:=(body->>'member_id')::uuid;
  select * into p from nyacro_players.players where id=uid;
  kind:=case when p.platform='pc' then 'pc' else coalesce(body->>'device_type',p.device_type,'mobile') end;
  if p.platform='mobile' and kind='pc' then raise check_violation using message='invalid device kind';end if;
  mask:=coalesce((body->>'used_devices')::integer,case when p.platform='pc' and p.device_type<>'pc' then 1 else p.used_devices end,case when kind='pc' then 1 else 2 end);
  mask:=mask | case kind when 'pc' then 1 when 'tablet' then 4 else 2 end;
  if op='players_register' or (body->>'seq')::bigint=p.seq then update nyacro_players.players set device_type=kind,used_devices=mask where id=uid;end if;
  select * into ledger from nyacro_players.completion_ledger where id=uid;
  if found and ledger.lifetime_completed>p.lifetime_completed then
   update nyacro_players.players set lifetime_completed=ledger.lifetime_completed where id=uid;
  end if;
  select * into p from nyacro_players.players where id=uid;
  insert into nyacro_players.completion_ledger(id,token_hash,nickname_key,lifetime_completed)
   values(uid,p.token_hash,normalize(btrim(p.nickname),NFC),p.lifetime_completed)
   on conflict(id) do update set nickname_key=excluded.nickname_key,
    lifetime_completed=greatest(nyacro_players.completion_ledger.lifetime_completed,excluded.lifetime_completed)
 where nyacro_players.completion_ledger.nickname_key is distinct from excluded.nickname_key
 or nyacro_players.completion_ledger.lifetime_completed<excluded.lifetime_completed;
  page_value:=(result->>'offset')::integer;
  select count(distinct (normalize(btrim(nickname),NFC) collate "C")) into total
   from nyacro_players.players where present and last_seen>now()-interval '60 seconds';
  with active as materialized (
   select pp.*,normalize(btrim(pp.nickname),NFC) collate "C" as name_key
    from nyacro_players.players pp where pp.present and pp.last_seen>now()-interval '60 seconds'
  ), grouped as (
   select name_key,(array_agg(id order by (id=uid) desc,id))[1] as representative,
    bool_or(running) as running,least(1000000000,sum(completed))::bigint as completed,
    jsonb_agg(distinct device_type order by device_type) as devices,
    coalesce(jsonb_agg(distinct content order by content) filter(where content<>''),'[]'::jsonb) as contents
   from active group by name_key order by name_key limit 100 offset page_value
  ), totals as (
   select l.nickname_key,least(9000000000000000,sum(l.lifetime_completed))::bigint as lifetime_completed
    from nyacro_players.completion_ledger l join grouped g on g.name_key=l.nickname_key group by l.nickname_key
  )
  select coalesce(jsonb_agg(jsonb_build_object('id',a.id,'nickname',g.name_key,'platform',a.platform,
   'device_type',a.device_type,'device_types',g.devices,'status',case when g.running then 'running' else 'stopped' end,
   'content',case when jsonb_array_length(g.contents)=1 then g.contents->>0 else '' end,'contents',g.contents,
   'completed',g.completed,'lifetime_completed',coalesce(t.lifetime_completed,0)) order by g.name_key),'[]'::jsonb)
   into rows from grouped g join active a on a.id=g.representative left join totals t on t.nickname_key=g.name_key;
  -- Never return a nickname-group total as self: clients merge self into their
  -- installation's next upload, which would repeatedly multiply shared totals.
  return result||jsonb_build_object('players',rows,'total',total,'grouped_by_nickname',true,
   'self_used_devices',p.used_devices,'self_lifetime_completed',p.lifetime_completed);
 end if;
 if op is null or op not in ('diagnostics_submit','admin_list_errors','admin_read_error','admin_mark_read')
  or coalesce(body->>'member_id','') !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
  or coalesce(body->>'token','') !~ '^[a-f0-9]{64}$' then return jsonb_build_object('error','invalid_request');end if;
 uid:=(body->>'member_id')::uuid;
 select * into p from nyacro_players.players where id=uid;
 if not found or p.token_hash<>extensions.digest(body->>'token','sha256') then return jsonb_build_object('error','unauthorized');end if;
 bucket_value:=floor(extract(epoch from clock_timestamp())/600)::bigint;
 insert into nyacro_rooms.limits(key,bucket,hits) values(op||':'||uid::text,bucket_value,1)
 on conflict(key,bucket) do update set hits=nyacro_rooms.limits.hits+1 returning nyacro_rooms.limits.hits into hits;
 if hits>(case when op='diagnostics_submit' then 20 else 120 end) then return jsonb_build_object('error','rate_limit');end if;
 if op='diagnostics_submit' then
  report:=body->'report';
  if body->'consent' is distinct from 'true'::jsonb or jsonb_typeof(report) is distinct from 'object'
   or coalesce(report->>'id','') !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
   or coalesce(report->>'occurred_at','') !~ '^[0-9]{1,13}$'
   or coalesce(report->>'app_version','') !~ '^[0-9A-Za-z._-]{1,32}$'
   or coalesce(report->>'device_type','') not in ('pc','mobile','tablet')
   or coalesce(report->>'screen','') !~ '^[0-9]{1,5}x[0-9]{1,5}$'
   or char_length(coalesce(report->>'device_model',''))>80
   or char_length(coalesce(report->>'stop_reason','')) not between 1 and 240
   or char_length(coalesce(report->>'logs',''))>4000
   or coalesce(report->>'content','') not in ('어비스','레이드') then return jsonb_build_object('error','invalid_request');end if;
  kind:=report->>'device_type';if (p.platform='pc' and kind<>'pc') or (p.platform='mobile' and kind='pc') then return jsonb_build_object('error','invalid_request');end if;
  rid:=(report->>'id')::uuid;select * into received from nyacro_players.error_reports where id=rid;
  if found then if received.player_id is distinct from uid then return jsonb_build_object('error','unauthorized');end if;return jsonb_build_object('ok',true,'report_id',rid);end if;
  insert into nyacro_players.error_reports(id,player_id,nickname,platform,device_type,app_version,device_model,screen,content,stop_reason,logs,occurred_at)
   values(rid,uid,p.nickname,p.platform,kind,report->>'app_version',nyacro_players.scrub(report->>'device_model',80),report->>'screen',report->>'content',nyacro_players.scrub(report->>'stop_reason',240),nyacro_players.scrub(report->>'logs',4000),to_timestamp((report->>'occurred_at')::bigint/1000.0));
  return jsonb_build_object('ok',true,'report_id',rid);
 end if;
 select a.key_hash into key_hash from nyacro_players.admin_keys a where a.id=1 and a.enabled;
 if not found then return jsonb_build_object('error','admin_unconfigured');end if;
 if coalesce(body->>'admin_key','') !~ '^[a-f0-9]{64}$' or key_hash<>extensions.digest(body->>'admin_key','sha256') then return jsonb_build_object('error','admin_required');end if;
 if op='admin_list_errors' then
  if coalesce(body->>'offset','') !~ '^[0-9]{1,5}$' or jsonb_typeof(body->'unread_only') is distinct from 'boolean' then return jsonb_build_object('error','invalid_request');end if;
  page_value:=(body->>'offset')::integer;if page_value>10000 then return jsonb_build_object('error','invalid_request');end if;only_unread:=(body->>'unread_only')::boolean;
  select count(*) into total from nyacro_players.error_reports where not only_unread or read_at is null;
  select coalesce(jsonb_agg(jsonb_build_object('id',r.id,'nickname',r.nickname,'device_type',r.device_type,'app_version',r.app_version,'content',r.content,'stop_reason',r.stop_reason,'occurred_at',r.occurred_at,'read',r.read_at is not null) order by r.received_at desc,r.id),'[]'::jsonb) into rows
   from (select * from nyacro_players.error_reports where not only_unread or read_at is null order by received_at desc,id limit 20 offset page_value) r;
  return jsonb_build_object('ok',true,'reports',rows,'offset',page_value,'total',total);
 end if;
 if coalesce(body->>'report_id','') !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' then return jsonb_build_object('error','invalid_request');end if;
 rid:=(body->>'report_id')::uuid;
 if op='admin_mark_read' then update nyacro_players.error_reports set read_at=coalesce(read_at,clock_timestamp()) where id=rid;return jsonb_build_object('ok',true);end if;
 select * into received from nyacro_players.error_reports where id=rid;
 if not found then return jsonb_build_object('error','invalid_request');end if;
 return jsonb_build_object('ok',true,'report',jsonb_build_object('id',received.id,'nickname',received.nickname,'platform',received.platform,'device_type',received.device_type,'app_version',received.app_version,'device_model',received.device_model,'screen',received.screen,'content',received.content,'stop_reason',received.stop_reason,'logs',received.logs,'occurred_at',received.occurred_at,'received_at',received.received_at,'read',received.read_at is not null));
exception when invalid_text_representation or numeric_value_out_of_range or check_violation or datetime_field_overflow then
 return jsonb_build_object('error','invalid_request');
end;
$$;
revoke all on function public.nyacro_players_dispatch(jsonb,text) from public,anon,authenticated;
grant execute on function public.nyacro_players_dispatch(jsonb,text) to service_role;
commit;
