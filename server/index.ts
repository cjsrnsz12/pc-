// No SDK or external dependencies. The privileged key stays in this server's runtime.
const headers = {"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store"};
const errors: Record<string,string> = {
 invalid_request:"요청 내용을 확인해 주세요.", unauthorized:"방 참여 정보가 만료되었습니다. 다시 참여해 주세요.",
 player_capacity:"지금은 등록할 수 없습니다. 잠시 후 다시 시도해 주세요.", room_not_found:"방 코드를 확인해 주세요.", room_full:"이 방의 참여 인원이 가득 찼습니다.",
 rate_limit:"요청이 많습니다. 잠시 후 다시 시도해 주세요.", room_capacity:"지금은 새 방을 만들 수 없습니다. 잠시 후 다시 시도해 주세요."
};
function reply(data:unknown,status=200){return new Response(JSON.stringify(data),{status,headers});}
async function readBody(req:Request){
 const reader=req.body?.getReader();if(!reader)throw Error("invalid_request");
 const chunks:Uint8Array[]=[];let size=0;
 while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>8192){await reader.cancel();throw Error("invalid_request");}chunks.push(value);}
 const all=new Uint8Array(size);let at=0;for(const chunk of chunks){all.set(chunk,at);at+=chunk.byteLength;}
 const body=JSON.parse(new TextDecoder().decode(all));
 if(!body||typeof body!=="object"||Array.isArray(body))throw Error("invalid_request");return body;
}
Deno.serve(async(req:Request)=>{
 if(req.method==="GET")return reply({service:"nyacro-rooms",protocol:2,legacy_protocol:1});
 if(req.method!=="POST")return reply({error:"method_not_allowed"},405);
 try{
  const body=await readBody(req);
  const players=["players_register","players_sync","players_remove"].includes(body.op);
  if(!players&&!["create","join","sync","leave"].includes(body.op))return reply({error:"invalid_request",message:errors.invalid_request},400);
  const service=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")||JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS")||"{}").default;
  const origin=Deno.env.get("SUPABASE_URL");if(!service||!origin)return reply({error:"unavailable",message:"공유 서버 연결을 잠시 후 다시 시도해 주세요."},503);
  const ip=req.headers.get("x-real-ip")||req.headers.get("x-forwarded-for")?.split(",").at(-1)?.trim()||"unknown";
  const key=await crypto.subtle.importKey("raw",new TextEncoder().encode(service),{name:"HMAC",hash:"SHA-256"},false,["sign"]);
  const digest=new Uint8Array(await crypto.subtle.sign("HMAC",key,new TextEncoder().encode(ip)));
  const rateKey=Array.from(digest,b=>b.toString(16).padStart(2,"0")).join("");
  const rpcHeaders:Record<string,string>={"apikey":service,"Content-Type":"application/json"};
  if(service.startsWith("eyJ"))rpcHeaders.Authorization="Bearer "+service;
  const response=await fetch(origin+"/rest/v1/rpc/"+(players?"nyacro_players_dispatch":"nyacro_rooms_dispatch"),{method:"POST",headers:rpcHeaders,body:JSON.stringify({body,rate_key:rateKey}),signal:AbortSignal.timeout(6000)});
  if(!response.ok)return reply({error:"unavailable",message:"공유 서버 연결을 잠시 후 다시 시도해 주세요."},503);
  const data=await response.json();
  if(data.error){const code=Object.hasOwn(errors,data.error)?data.error:"invalid_request";return reply({error:code,message:errors[code]},code==="unauthorized"?403:code==="rate_limit"?429:400);}
  return reply(data);
 }catch{return reply({error:"invalid_request",message:errors.invalid_request},400);}
});
