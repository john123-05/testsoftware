import {serviceClient} from './supabase.ts';
import type {MachineAuth} from './auth.ts';
export const ONLINE_BUCKET='online-photo-originals';
export async function onlineStream(auth:MachineAuth, cameraCode:string){
 const db=serviceClient();
 const {data,error}=await db.from('liftpic_machine_configs').select('mode,settings,legacy_customer_code,parks(slug)').eq('machine_id',auth.machineId).eq('park_id',auth.parkId).eq('camera_code',cameraCode).eq('is_active',true).maybeSingle();
 if(error)throw new Error('Cannot read approved camera');
 if(data?.settings?.online_sales!==true)return null;
 if(!auth.secured||data.mode!=='all_photos')throw new Error('Private online upload requires approved device authentication');
 const shop=await db.from('online_photo_shops').select('park_id').eq('park_id',auth.parkId).maybeSingle();
 if(shop.error||!shop.data)throw new Error('Online photo shop not configured');
 return data;
}
export async function commitOnlinePhoto(auth:MachineAuth,event:any,path:string){
 const db=serviceClient();
 if(!await onlineStream(auth,event.camera_code)||event.park_id!==auth.parkId||event.processed_storage_path!==path||event.metadata?.upload_bucket!==ONLINE_BUCKET)throw new Error('Unapproved online photo target');
 const code=String(event.legacy_filename??'').replace(/\.jpg$/i,'');
 const checksum=String(event.metadata?.checksum_sha256??'');
 if(!/^\d{16}$/.test(code)||!/^([0-9a-f]{64})$/.test(checksum)||!path.startsWith(auth.parkId+'/'))throw new Error('Invalid online photo identity');
 const {data:original,error}=await db.storage.from(ONLINE_BUCKET).download(path);
 if(error||!original||original.size>25000000)throw new Error('Online original missing');
 const bytes=await original.arrayBuffer();
 const actual=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
 const jpeg=new Uint8Array(bytes);
 if(actual!==checksum||jpeg[0]!==255||jpeg[1]!==216)throw new Error('Online original checksum/type mismatch');
 const photo_number=/^\d{1,5}$/.test(String(event.capture_id??''))?String(event.capture_id).padStart(5,'0'):null;
 const row={photo_number,park_id:auth.parkId,machine_id:auth.machineId,camera_code:event.camera_code,claim_code:code,storage_path:path,checksum_sha256:checksum,captured_at:event.captured_at,is_test:event.metadata?.is_test===true};
 if(row.is_test){
  const result=await db.from('photo_events').update({upload_status:'uploaded',error:null}).eq('machine_id',auth.machineId).eq('event_key',event.metadata.event_key);
  if(result.error)throw result.error;
  return {ok:true,claimable:false,online_photo:true,external_code:code,sale_recorded:false,is_test:true};
 }
 const inserted=await db.from('online_photo_assets').upsert(row,{onConflict:'park_id,claim_code',ignoreDuplicates:true});
 if(inserted.error)throw new Error('Cannot register online original');
 const saved=await db.from('online_photo_assets').select('checksum_sha256,storage_path').eq('park_id',auth.parkId).eq('claim_code',code).single();
 if(saved.error||saved.data.checksum_sha256!==checksum||saved.data.storage_path!==path)throw new Error('Photo code collision: original remains unchanged');
 const update=await db.from('photo_events').update({upload_status:'uploaded',error:null}).eq('machine_id',auth.machineId).eq('event_key',event.metadata.event_key);
 if(update.error)throw update.error;
 return {ok:true,claimable:false,online_photo:true,external_code:code,sale_recorded:false};
}
