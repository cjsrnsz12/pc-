begin;
do $test$
declare a jsonb; b jsonb; r jsonb; test_code text; uid text:='ffeeddcc-0000-4000-8000-000000000001'; tok text:=repeat('a',64); rid uuid; i integer;
begin
 a:=jsonb_build_object('op','create','member_id',uid,'token',tok,'nickname','검증','platform','mobile','app_version','1.2.36');
 r:=public.nyacro_rooms_dispatch(a,repeat('1',64)); assert (r->>'ok')::boolean;
 test_code:=r->>'room_code';
 assert r::text !~ 'token|token_hash|rate_key';
 assert public.nyacro_rooms_dispatch(a,repeat('1',64))->>'room_code'=test_code;
 b:=jsonb_build_object('op','sync','member_id',uid,'token',tok,'seq',1,'running',true,'completed',15,'content','어비스','run_id','1');
 r:=public.nyacro_rooms_dispatch(b,repeat('1',64));assert r->'members'->0->>'status'='running';assert r->'members'->0->>'completed'='15';
 r:=public.nyacro_rooms_dispatch(b||'{"seq":2,"completed":3}'::jsonb,repeat('1',64));assert r->'members'->0->>'completed'='15';
 r:=public.nyacro_rooms_dispatch(b||'{"seq":3,"completed":0,"run_id":"2","running":false}'::jsonb,repeat('1',64));assert r->'members'->0->>'completed'='0';assert r->'members'->0->>'status'='stopped';
 r:=public.nyacro_rooms_dispatch(b||'{"seq":2,"completed":400}'::jsonb,repeat('1',64));assert r->'members'->0->>'completed'='0';
 update nyacro_rooms.members set last_seen=now()-interval '70 seconds' where id=uid::uuid;
 r:=public.nyacro_rooms_dispatch(b||'{"seq":2}'::jsonb,repeat('1',64));assert r->'members'->0->>'status'='offline';
 assert public.nyacro_rooms_dispatch(b||'{"completed":-1}'::jsonb,repeat('1',64))->>'error'='invalid_request';
 assert public.nyacro_rooms_dispatch(b||'{"running":"true"}'::jsonb,repeat('1',64))->>'error'='invalid_request';
 assert public.nyacro_rooms_dispatch(b||jsonb_build_object('token',repeat('b',64)),repeat('1',64))->>'error'='unauthorized';
 select id into rid from nyacro_rooms.rooms where rooms.code=test_code;
 for i in 1..49 loop insert into nyacro_rooms.members(id,room_id,token_hash,nickname,platform,app_version) values(gen_random_uuid(),rid,extensions.digest(tok,'sha256'),'capacity','pc','test');end loop;
 r:=public.nyacro_rooms_dispatch(a||jsonb_build_object('op','join','member_id',gen_random_uuid()::text,'room_code',test_code),repeat('2',64));assert r->>'error'='room_full';
 assert not has_function_privilege('anon','public.nyacro_rooms_dispatch(jsonb,text)','execute');
 assert not has_function_privilege('authenticated','public.nyacro_rooms_dispatch(jsonb,text)','execute');
 assert not has_schema_privilege('anon','nyacro_rooms','usage');
 assert not has_table_privilege('authenticated','nyacro_rooms.members','select');
end $test$;
rollback;
select 'PASS room isolation, credentials, sequence, monotonic count, reset, offline, capacity and grants' as result;
