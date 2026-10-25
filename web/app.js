import * as THREE from 'three';
import {OrbitControls} from 'three/addons/OrbitControls.js';
import {createIcons, RotateCcw, Circle, Square} from '/static/vendor/lucide.js';
document.querySelector('#reset').innerHTML='<i data-lucide="rotate-ccw"></i>';
document.querySelector('#record').innerHTML='<i data-lucide="circle"></i> Record';
document.querySelector('#stop').innerHTML='<i data-lucide="square"></i> Stop';
createIcons({icons:{RotateCcw,Circle,Square}});
const names=['thumb','index','middle','ring','pinky'];
document.querySelector('#curls').innerHTML=names.map(n=>`<div class="curl">${n.toUpperCase()}<strong id="${n}">--</strong><div class="bar"><i id="${n}bar"></i></div></div>`).join('');
const viewport=document.querySelector('#viewport'), scene=new THREE.Scene();
scene.background=new THREE.Color('#141b17');
const camera=new THREE.PerspectiveCamera(43,1,.1,100);
const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
renderer.toneMapping=THREE.ACESFilmicToneMapping;
renderer.setPixelRatio(Math.min(devicePixelRatio,2));viewport.appendChild(renderer.domElement);
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;
function reset(){camera.position.set(0,2.2,9);controls.target.set(0,.7,0);controls.update();}reset();
document.querySelector('#reset').onclick=reset;
scene.add(new THREE.HemisphereLight(0xe8fff0,0x334738,2.2));
const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(3,5,5);scene.add(light);
const fill=new THREE.DirectionalLight(0x87aee5,2);fill.position.set(-4,2,-3);scene.add(fill);
const grid=new THREE.GridHelper(14,28,0x577565,0x29392f);grid.position.y=-2.1;scene.add(grid);
document.querySelector('#grid').onchange=e=>grid.visible=e.target.checked;
const edges=[[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];
const jointGeometry=new THREE.SphereGeometry(.065,16,12), segmentGeometry=new THREE.CylinderGeometry(.043,.055,1,12);
const models=new Map(), yAxis=new THREE.Vector3(0,1,0);
function makeHand(id,index){
 const group=new THREE.Group();scene.add(group);
 const metal=new THREE.MeshStandardMaterial({color:index?0x8daed1:0xa1b9a9,metalness:.7,roughness:.32});
 const jointMat=new THREE.MeshStandardMaterial({color:index?0x74b8ff:0x93edb2,metalness:.4,roughness:.3});
 const joints=Array.from({length:21},()=>{const m=new THREE.Mesh(jointGeometry,jointMat);group.add(m);return m;});
 const segments=edges.map(()=>{const m=new THREE.Mesh(segmentGeometry,metal);group.add(m);return m;});
 const palm=new THREE.Mesh(new THREE.BoxGeometry(1,1,.16),metal);group.add(palm);
 const plate=new THREE.Mesh(new THREE.BoxGeometry(.65,.6,.025),new THREE.MeshStandardMaterial({color:0x26372d,metalness:.5,roughness:.4}));palm.add(plate);plate.position.z=.095;
 const wrist=new THREE.Mesh(new THREE.CylinderGeometry(.17,.19,.3,16),metal);group.add(wrist);
 const model={group,joints,segments,palm,wrist};models.set(id,model);return model;
}
function applyState(state){
 const active=new Set();
 for(const [index,hand] of state.robot_hands.entries()){
  const id=hand.track_id;active.add(id);const m=models.get(id)||makeHand(id,index);
  m.group.visible=true;const points=hand.landmarks.map(p=>new THREE.Vector3(...p));
  points.forEach((p,i)=>m.joints[i].position.copy(p));
  edges.forEach(([a,b],i)=>{const delta=points[b].clone().sub(points[a]);const segment=m.segments[i];segment.position.copy(points[a]).add(points[b]).multiplyScalar(.5);segment.scale.y=delta.length();segment.quaternion.setFromUnitVectors(yAxis,delta.normalize());});
  const v=hand.palm_orientation, matrix=new THREE.Matrix4().set(v[0],v[3],v[6],0,v[1],v[4],v[7],0,v[2],v[5],v[8],0,0,0,0,1);
  m.palm.position.set(...hand.palm_position);m.palm.quaternion.setFromRotationMatrix(matrix);
  m.palm.scale.set(Math.max(.3,hand.palm_width*.82),Math.max(.3,hand.palm_length*.7),1);
  m.wrist.position.copy(points[0]);m.wrist.quaternion.copy(m.palm.quaternion);
 }
 for(const [id,m] of models)m.group.visible=active.has(id);
}
let ws,latest=null,lastArrival=0,lastFrame=-1,clockOffset=0,pingStart=0,rtt=null;
let metrics={frames:0,latency:null,rtt:null};window.liveDiagnostics={metrics,models,renderer,scene,camera};
function connect(){
 ws=new WebSocket(`ws://${location.host}/ws`);
 ws.onopen=()=>{pingStart=Date.now();ws.send(JSON.stringify({type:'ping',client_ms:pingStart}));};
 ws.onmessage=e=>{const data=JSON.parse(e.data);if(data.type==='pong'){rtt=Date.now()-pingStart;clockOffset=data.server_ms-(pingStart+Date.now())/2;ws.send(JSON.stringify({type:'next'}));return;}latest=data;lastArrival=performance.now();};
 ws.onclose=()=>{document.querySelector('#connection').textContent='DISCONNECTED';document.querySelector('#connection').className='';setTimeout(connect,1000);};
 ws.onerror=()=>ws.close();
}connect();
let previewBusy=false;
async function updatePreview(){if(previewBusy)return;previewBusy=true;try{const response=await fetch('/api/preview',{cache:'no-store'});const blob=await response.blob();if(blob.size){const img=document.querySelector('#preview'),old=img.src;img.src=URL.createObjectURL(blob);if(old.startsWith('blob:'))URL.revokeObjectURL(old);}}finally{previewBusy=false;}}
setInterval(()=>updatePreview().catch(()=>{}),100);
function display(state){
 applyState(state);const hand=state.hands[0];
 const age=Math.max(0,Date.now()+clockOffset-(state.captured_unix_ms??Date.now()));
 metrics.frames++;metrics.latency=age;metrics.rtt=rtt;
 const values={fps:(state.fps??0).toFixed(1),latency:`${Math.round(age)} ms`,hand:state.hands.map(h=>h.handedness.toUpperCase()).join(' + ')||'--',pose:hand?.grip_pose||'--',confidence:hand?.confidence!=null?`${(hand.confidence*100).toFixed(0)}%`:'--',camera:state.camera??'CAMO',session:state.recording?`REC / ${state.session}`:'READY'};
 for(const [id,value] of Object.entries(values))document.getElementById(id).textContent=value;
 document.querySelector('#connection').textContent=state.status;document.querySelector('#connection').className=hand?'live':'';
 document.querySelector('#lost').textContent=hand?'':state.status;
 document.querySelector('#cameraStatus').textContent='';
 document.querySelector('#record').disabled=state.recording;document.querySelector('#stop').disabled=!state.recording;
 for(const n of names){document.getElementById(n).textContent=hand?hand.curls[n].toFixed(2):'--';document.getElementById(n+'bar').style.width=`${hand?hand.curls[n]*100:0}%`;}
}
for(const [id,action] of [['record','start'],['stop','stop']])document.getElementById(id).onclick=async()=>{await fetch(`/api/record/${action}`,{method:'POST'});};
new ResizeObserver(()=>{const {width,height}=viewport.getBoundingClientRect();renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();}).observe(viewport);
renderer.setAnimationLoop(()=>{
 if(latest){if(latest.frame_id!==lastFrame){display(latest);lastFrame=latest.frame_id;}latest=null;if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'next'}));}
 if(performance.now()-lastArrival>1000){document.querySelector('#connection').textContent=ws?.readyState===WebSocket.OPEN?'TRACKING STALE':'DISCONNECTED';document.querySelector('#lost').textContent='TRACKING LOST';for(const m of models.values())m.group.visible=false;}
 controls.update();renderer.render(scene,camera);
});
