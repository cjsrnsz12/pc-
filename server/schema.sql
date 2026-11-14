-- Only the Edge Function's server-side service role can call this contract.
-- App clients receive opaque per-membership credentials, never a database secret.
create schema if not exists nyacro_rooms;
revoke all on schema nyacro_rooms from public, anon, authenticated;
grant usage on schema nyacro_rooms to service_role;

create table nyacro_rooms.rooms (
 id uuid primary key default gen_random_uuid(),
 code text not null unique check (code ~ '^[0-9A-F]{20}$'),
 created_at timestamptz not null default now()
);
create table nyacro_rooms.members (
 id uuid primary key,
 room_id uuid not null references nyacro_rooms.rooms(id) on delete cascade,
 token_hash bytea not null,
 nickname text not null check (char_length(nickname) between 1 and 20),
 platform text not null check (platform in ('mobile','pc')),
 app_version text not null,
 running boolean not null default false,
 content text not null default '',
 completed integer not null default 0 check (completed between 0 and 1000000000),
 run_id text not null default '',
 seq bigint not null default -1,
 last_seen timestamptz not null default now()
);
create index members_room_seen on nyacro_rooms.members(room_id,last_seen);
create table nyacro_rooms.limits (
 key text not null,
 bucket bigint not null,
 hits integer not null,
 primary key(key,bucket)
);
alter table nyacro_rooms.rooms enable row level security;
alter table nyacro_rooms.members enable row level security;
alter table nyacro_rooms.limits enable row level security;
revoke all on all tables in schema nyacro_rooms from public, anon, authenticated;
grant select,insert,update,delete on all tables in schema nyacro_rooms to service_role;

create or replace function public.nyacro_rooms_dispatch(body jsonb,rate_key text)
returns jsonb language plpgsql security invoker set search_path='' set statement_timeout='5s'
as $$
declare
 op text:=body->>'op'; uid uuid; secret text:=body->>'token'; nick text;
 requested_code text; room uuid; code text; existing nyacro_rooms.members%rowtype;
 bucket_value bigint:=floor(extract(epoch from clock_timestamp())/600)::bigint;
 hits integer; limit_count integer; seq_value bigint; count_value bigint; rows jsonb;
begin
 if op is null or op not in ('create','join','sync','leave') or coalesce(rate_key,'') !~ '^[0-9a-f]{64}$'
    or coalesce(body->>'member_id','') !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    or coalesce(secret,'') !~ '^[0-9a-f]{64}$' then
  return jsonb_build_object('error','invalid_request');
 end if;
 uid:=(body->>'member_id')::uuid;
 limit_count:=case op when 'create' then 5 when 'join' then 120 else 6000 end;
 insert into nyacro_rooms.limits(key,bucket,hits) values(op||':'||rate_key,bucket_value,1)
 on conflict(key,bucket) do update set hits=nyacro_rooms.limits.hits+1
 returning nyacro_rooms.limits.hits into hits;
 if hits>limit_count then return jsonb_build_object('error','rate_limit'); end if;

 select * into existing from nyacro_rooms.members where id=uid for update;
 if found then
  if existing.token_hash<>extensions.digest(secret,'sha256') then
   return jsonb_build_object('error','unauthorized');
  end if;
  room:=existing.room_id;
 elsif op in ('sync','leave') then
  return jsonb_build_object('error','unauthorized');
 end if;

 if op in ('create','join') then
  nick:=btrim(body->>'nickname');
  if nick is null or char_length(nick) not between 1 and 20 or nick ~ '[[:cntrl:]]'
   or coalesce(body->>'platform','') not in ('mobile','pc')
   or coalesce(body->>'app_version','') !~ '^[0-9A-Za-z._-]{1,32}$' then
   return jsonb_build_object('error','invalid_request');
  end if;
  if op='join' then
   requested_code:=upper(regexp_replace(coalesce(body->>'room_code',''),'[ -]','','g'));
   if requested_code !~ '^[0-9A-F]{20}$' then return jsonb_build_object('error','room_not_found'); end if;
  end if;
  if room is not null then
   -- A retry after a dropped response resumes the same membership; it creates no duplicate.
   select r.code into code from nyacro_rooms.rooms r where r.id=room;
   if op='join' and code<>requested_code then return jsonb_build_object('error','unauthorized'); end if;
  else
   if op='create' then
    perform pg_advisory_xact_lock(723901,1);
    delete from nyacro_rooms.members where last_seen<now()-interval '7 days';
    delete from nyacro_rooms.rooms r where r.created_at<now()-interval '1 day'
     and not exists(select 1 from nyacro_rooms.members m where m.room_id=r.id);
    delete from nyacro_rooms.limits where bucket<floor(extract(epoch from clock_timestamp())/600)::bigint-2;
    if (select count(*) from nyacro_rooms.rooms)>=1000 then return jsonb_build_object('error','room_capacity'); end if;
    code:=upper(encode(extensions.gen_random_bytes(10),'hex'));
    insert into nyacro_rooms.rooms(code) values(code) returning id into room;
   else
    select r.id,r.code into room,code from nyacro_rooms.rooms r where r.code=requested_code for update;
    if room is null then return jsonb_build_object('error','room_not_found'); end if;
   end if;
   if (select count(*) from nyacro_rooms.members m where m.room_id=room and m.last_seen>now()-interval '1 day')>=50 then
    return jsonb_build_object('error','room_full');
   end if;
   insert into nyacro_rooms.members(id,room_id,token_hash,nickname,platform,app_version)
    values(uid,room,extensions.digest(secret,'sha256'),nick,body->>'platform',body->>'app_version');
  end if;
 elsif op='leave' then
  delete from nyacro_rooms.members where id=uid;
  return jsonb_build_object('ok',true);
 else
  if coalesce(body->>'seq','') !~ '^[0-9]{1,16}$'
   or coalesce(body->>'completed','') !~ '^[0-9]{1,10}$'
   or jsonb_typeof(body->'running') is distinct from 'boolean'
   or coalesce(body->>'content','') not in ('','어비스','레이드')
   or coalesce(body->>'run_id','') !~ '^[0-9a-fA-F-]{0,36}$' then
   return jsonb_build_object('error','invalid_request');
  end if;
  seq_value:=(body->>'seq')::bigint;count_value:=(body->>'completed')::bigint;
  if seq_value>9000000000000000 or count_value>1000000000 then return jsonb_build_object('error','invalid_request'); end if;
  if seq_value>existing.seq then
   update nyacro_rooms.members set
    running=(body->>'running')::boolean,content=body->>'content',run_id=body->>'run_id',seq=seq_value,
    completed=case when run_id=body->>'run_id' then greatest(completed,count_value) else count_value end,
    last_seen=clock_timestamp()
   where id=uid;
  end if;
  select r.code into code from nyacro_rooms.rooms r where r.id=room;
 end if;

 select coalesce(jsonb_agg(jsonb_build_object(
  'id',m.id,'nickname',m.nickname,'platform',m.platform,'app_version',m.app_version,
  'status',case when m.last_seen<now()-interval '60 seconds' then 'offline' when m.running then 'running' else 'stopped' end,
  'content',m.content,'completed',m.completed,'last_seen',m.last_seen)
  order by m.nickname,m.platform,m.id),'[]'::jsonb) into rows
 from nyacro_rooms.members m where m.room_id=room and m.last_seen>now()-interval '1 day';
 return jsonb_build_object('ok',true,'protocol',1,'room_code',code,'members',rows,'server_time',clock_timestamp());
end;
$$;
revoke all on function public.nyacro_rooms_dispatch(jsonb,text) from public,anon,authenticated;
grant execute on function public.nyacro_rooms_dispatch(jsonb,text) to service_role;
