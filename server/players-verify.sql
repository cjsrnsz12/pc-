-- Run only after the protocol2 migration; every test change rolls back.
begin;
do $test$
declare uid text:=gen_random_uuid()::text;secret text:=repeat('a',64);body jsonb;r jsonb;before_rooms integer;i integer;
begin
 select count(*) into before_rooms from nyacro_rooms.members;
 body:=jsonb_build_object('op','players_register','member_id',uid,'token',secret,'nickname','검증공개','platform','mobile','app_version','1.2.37','consent_version',2,'offset',0);
 assert public.nyacro_players_dispatch(body-'consent_version',repeat('3',64))->>'error'='invalid_request';
 r:=public.nyacro_players_dispatch(body,repeat('3',64));assert r->>'protocol'='2';assert r->>'page_size'='100';
 assert not (r::text ~ 'token|token_hash|rate_key');
 r:=public.nyacro_players_dispatch(body,repeat('3',64));assert (select count(*) from nyacro_players.players where id=uid::uuid)=1;
 body:=jsonb_build_object('op','players_sync','member_id',uid,'token',secret,'seq',1,'running',true,'present',true,'completed',27,'content','어비스','run_id','1','offset',0);
 perform public.nyacro_players_dispatch(body,repeat('3',64));assert (select completed from nyacro_players.players where id=uid::uuid)=27;
 perform public.nyacro_players_dispatch(body||'{"seq":2,"completed":2}'::jsonb,repeat('3',64));assert (select completed from nyacro_players.players where id=uid::uuid)=27;
 perform public.nyacro_players_dispatch(body||'{"seq":3,"completed":0,"run_id":"2","running":false}'::jsonb,repeat('3',64));assert (select completed=0 and not running from nyacro_players.players where id=uid::uuid);
 perform public.nyacro_players_dispatch(body||'{"seq":2,"completed":99}'::jsonb,repeat('3',64));assert (select completed from nyacro_players.players where id=uid::uuid)=0;
 assert public.nyacro_players_dispatch(body||jsonb_build_object('token',repeat('b',64)),repeat('3',64))->>'error'='unauthorized';
 assert public.nyacro_players_dispatch(body||'{"offset":-1}'::jsonb,repeat('3',64))->>'error'='invalid_request';
 for i in 1..205 loop
  insert into nyacro_players.players(id,token_hash,nickname,platform,app_version,consent_version) values(gen_random_uuid(),extensions.digest(secret,'sha256'),'검증페이지'||lpad(i::text,3,'0'),'pc','1.1.46',2);
 end loop;
 r:=public.nyacro_players_dispatch(body||'{"seq":4,"offset":0}'::jsonb,repeat('3',64));assert jsonb_array_length(r->'players')=100;assert (r->>'total')::integer>=206;
 r:=public.nyacro_players_dispatch(body||'{"seq":5,"offset":100}'::jsonb,repeat('3',64));assert jsonb_array_length(r->'players')=100;assert r->>'offset'='100';
 perform public.nyacro_players_dispatch(body||'{"seq":6,"present":false}'::jsonb,repeat('3',64));assert (select not present from nyacro_players.players where id=uid::uuid);
 update nyacro_players.players set last_seen=now()-interval '70 seconds' where nickname like '검증페이지%';
 r:=public.nyacro_players_dispatch(body||'{"seq":6}'::jsonb,repeat('3',64));assert not (r->'players' @> jsonb_build_array(jsonb_build_object('id',uid)));
 assert not has_schema_privilege('anon','nyacro_players','usage');
 assert not has_table_privilege('authenticated','nyacro_players.players','select');
 assert not has_function_privilege('anon','public.nyacro_players_dispatch(jsonb,text)','execute');
 assert not has_function_privilege('authenticated','public.nyacro_players_dispatch(jsonb,text)','execute');
 assert before_rooms=(select count(*) from nyacro_rooms.members);
end $test$;
rollback;
select 'PASS consent, shared list, paging, identity, sequence, count, stop, offline, private-room isolation and grants' as result;
