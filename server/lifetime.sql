-- Preserve currently stored counts; older reset history was never retained.
alter table nyacro_players.players add column lifetime_completed bigint not null default 0 check(lifetime_completed between 0 and 9000000000000000);
update nyacro_players.players set lifetime_completed=completed;

create or replace function public.nyacro_players_dispatch(body jsonb,rate_key text)
returns jsonb language plpgsql security invoker set search_path='' set statement_timeout='5s'
as $$
declare
 op text:=body->>'op';uid uuid;secret text:=body->>'token';nick text;
 existing nyacro_players.players%rowtype;hits integer;limit_count integer;
 bucket_value bigint:=floor(extract(epoch from clock_timestamp())/600)::bigint;
 seq_value bigint;count_value bigint;life_value bigint;page_value integer;rows jsonb;total integer;
begin
 if op is null or op not in ('players_register','players_sync','players_remove')
  or coalesce(rate_key,'') !~ '^[0-9a-f]{64}$'
  or coalesce(body->>'member_id','') !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
  or coalesce(secret,'') !~ '^[0-9a-f]{64}$' then return jsonb_build_object('error','invalid_request');end if;
 uid:=(body->>'member_id')::uuid;
 if body ? 'lifetime_completed' then
  if coalesce(body->>'lifetime_completed','') !~ '^[0-9]{1,16}$' then return jsonb_build_object('error','invalid_request');end if;
  life_value:=(body->>'lifetime_completed')::bigint;
  if life_value>9000000000000000 then return jsonb_build_object('error','invalid_request');end if;
 end if;
 limit_count:=case when op='players_register' then 120 else 6000 end;
 insert into nyacro_rooms.limits(key,bucket,hits) values(op||':'||rate_key,bucket_value,1)
 on conflict(key,bucket) do update set hits=nyacro_rooms.limits.hits+1 returning nyacro_rooms.limits.hits into hits;
 if hits>limit_count then return jsonb_build_object('error','rate_limit');end if;
 select * into existing from nyacro_players.players where id=uid for update;
 if found then
  if existing.token_hash<>extensions.digest(secret,'sha256') then return jsonb_build_object('error','unauthorized');end if;
 elsif op<>'players_register' then return jsonb_build_object('error','unauthorized');end if;
 if op='players_remove' then delete from nyacro_players.players where id=uid;return jsonb_build_object('ok',true);end if;
 if coalesce(body->>'offset','0') !~ '^[0-9]{1,5}$' then return jsonb_build_object('error','invalid_request');end if;
 page_value:=coalesce(body->>'offset','0')::integer;
 if page_value>10000 then return jsonb_build_object('error','invalid_request');end if;
 if op='players_register' then
  nick:=btrim(body->>'nickname');
  if nick is null or char_length(nick) not between 1 and 20 or nick ~ '[[:cntrl:]]'
   or coalesce(body->>'platform','') not in ('mobile','pc')
   or coalesce(body->>'app_version','') !~ '^[0-9A-Za-z._-]{1,32}$'
   or body->'consent_version' is distinct from '2'::jsonb then return jsonb_build_object('error','invalid_request');end if;
  if existing.id is null then
   perform pg_advisory_xact_lock(723901,2);
   delete from nyacro_players.players where last_seen<now()-interval '7 days';
   delete from nyacro_rooms.limits where bucket<bucket_value-2;
   if (select count(*) from nyacro_players.players)>=10000 then return jsonb_build_object('error','player_capacity');end if;
   insert into nyacro_players.players(id,token_hash,nickname,platform,app_version,consent_version,lifetime_completed)
    values(uid,extensions.digest(secret,'sha256'),nick,body->>'platform',body->>'app_version',2,coalesce(life_value,0));
  else
   if existing.platform<>body->>'platform' then return jsonb_build_object('error','invalid_request');end if;
   update nyacro_players.players set lifetime_completed=greatest(lifetime_completed,coalesce(life_value,0)),nickname=nick,app_version=body->>'app_version',present=true,last_seen=clock_timestamp() where id=uid;
  end if;
 else
  if coalesce(body->>'seq','') !~ '^[0-9]{1,16}$'
   or coalesce(body->>'completed','') !~ '^[0-9]{1,10}$'
   or jsonb_typeof(body->'running') is distinct from 'boolean'
   or jsonb_typeof(body->'present') is distinct from 'boolean'
   or coalesce(body->>'content','') not in ('','어비스','레이드')
   or coalesce(body->>'run_id','') !~ '^[0-9a-fA-F-]{0,36}$' then return jsonb_build_object('error','invalid_request');end if;
  seq_value:=(body->>'seq')::bigint;count_value:=(body->>'completed')::bigint;
  if seq_value>9000000000000000 or count_value>1000000000 then return jsonb_build_object('error','invalid_request');end if;
  if seq_value>existing.seq then
   update nyacro_players.players set running=(body->>'running')::boolean,present=(body->>'present')::boolean,
    lifetime_completed=case when life_value is not null then greatest(lifetime_completed,life_value)
     else least(9000000000000000,lifetime_completed+case when run_id=body->>'run_id' then greatest(0,count_value-completed) else count_value end) end,
    content=body->>'content',completed=case when run_id=body->>'run_id' then greatest(completed,count_value) else count_value end,
    run_id=body->>'run_id',seq=seq_value,last_seen=clock_timestamp() where id=uid;
  end if;
 end if;
 select count(*) into total from nyacro_players.players where present and last_seen>now()-interval '60 seconds';
 select coalesce(jsonb_agg(jsonb_build_object('id',p.id,'nickname',p.nickname,'platform',p.platform,
  'status',case when p.running then 'running' else 'stopped' end,'content',p.content,'completed',p.completed,'lifetime_completed',p.lifetime_completed)
  order by p.nickname,p.id),'[]'::jsonb) into rows from
  (select id,nickname,platform,running,content,completed,lifetime_completed from nyacro_players.players
   where present and last_seen>now()-interval '60 seconds' order by nickname,id limit 100 offset page_value) p;
 return jsonb_build_object('ok',true,'protocol',2,'players',rows,'total',total,'offset',page_value,'page_size',100,'self_lifetime_completed',(select lifetime_completed from nyacro_players.players where id=uid),'server_time',clock_timestamp());
end;
$$;
revoke all on function public.nyacro_players_dispatch(jsonb,text) from public,anon,authenticated;
grant execute on function public.nyacro_players_dispatch(jsonb,text) to service_role;
