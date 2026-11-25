import { Scene } from '@babylonjs/core/scene.js';
import { ArcRotateCamera } from '@babylonjs/core/Cameras/arcRotateCamera.js';
import { Vector3, Quaternion } from '@babylonjs/core/Maths/math.vector.js';
import { Color3, Color4 } from '@babylonjs/core/Maths/math.color.js';
import { PBRMaterial } from '@babylonjs/core/Materials/PBR/pbrMaterial.js';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial.js';
import { TransformNode } from '@babylonjs/core/Meshes/transformNode.js';
import { CreateBox } from '@babylonjs/core/Meshes/Builders/boxBuilder.js';
import { CreateCylinder } from '@babylonjs/core/Meshes/Builders/cylinderBuilder.js';
import { CreateSphere } from '@babylonjs/core/Meshes/Builders/sphereBuilder.js';
import { CreateGround } from '@babylonjs/core/Meshes/Builders/groundBuilder.js';
import { CreateLineSystem } from '@babylonjs/core/Meshes/Builders/linesBuilder.js';
import { HemisphericLight } from '@babylonjs/core/Lights/hemisphericLight.js';
import { DirectionalLight } from '@babylonjs/core/Lights/directionalLight.js';
import { ShadowGenerator } from '@babylonjs/core/Lights/Shadows/shadowGenerator.js';
import { LINE_CONFIG } from './config.js';

export const COLORS = { red: 0xe53935, yellow: 0xfdd835, blue: 0x1e88e5, unknown: 0x8493a4 };
export const PALLET_Z = { red: 2.4, blue: 3.5, yellow: 4.6 };
const color3 = (hex) => Color3.FromHexString(`#${hex.toString(16).padStart(6, '0')}`);

/** Three.js dosyasındaki ölçüler korunur. Sağ elli eksen sistemi aynı Z yönünü kullanır. */
export function createFactory(engine, canvas = null, { shadows = true } = {}) {
  const scene = new Scene(engine);
  scene.useRightHandedSystem = true;
  scene.clearColor = new Color4(0.914, 0.929, 0.949, 1);
  const camera = new ArcRotateCamera('Kamera', 0, 0, 18, new Vector3(0, 1, 2), scene);
  camera.setPosition(new Vector3(9, 7, 12));
  camera.fov = Math.PI / 4;
  camera.minZ = 0.05;
  camera.lowerRadiusLimit = 4;
  camera.upperRadiusLimit = 40;
  camera.upperBetaLimit = Math.PI / 2 - 0.03;
  camera.wheelPrecision = 35;
  camera.panningSensibility = 70;
  if (canvas) camera.attachControl(canvas, true);

  const ambient = new HemisphericLight('Ortam ışığı', new Vector3(0, 1, 0), scene);
  ambient.intensity = 0.8;
  ambient.groundColor = color3(0x7b8794);
  const sun = new DirectionalLight('Ana ışık', new Vector3(-6, -10, -8), scene);
  sun.position.set(6, 10, 8);
  sun.intensity = 1.5;
  const shadow = shadows ? new ShadowGenerator(2048, sun) : null;
  if (shadow) { shadow.usePercentageCloserFiltering = true; shadow.bias = 0.0004; }
  scene.imageProcessingConfiguration.exposure = 1;
  scene.imageProcessingConfiguration.toneMappingEnabled = true;
  const materials = new Map();
  function material(hex, metallic = 0.2, roughness = 0.45) {
    const key = `${hex}/${metallic}/${roughness}`;
    if (!materials.has(key)) {
      const mat = new PBRMaterial(`Malzeme ${key}`, scene);
      mat.albedoColor = color3(hex);
      mat.metallic = metallic;
      mat.roughness = roughness;
      materials.set(key, mat);
    }
    return materials.get(key);
  }
  function finish(mesh, pos, mat, parent) {
    mesh.position.copyFromFloats(...pos);
    mesh.material = mat;
    mesh.parent = parent || null;
    mesh.receiveShadows = true;
    shadow?.addShadowCaster(mesh);
    return mesh;
  }
  function box(name, size, pos, hex, metal = 0.2, parent, roughness = 0.45) {
    return finish(CreateBox(name, { width: size[0], height: size[1], depth: size[2] }, scene), pos, material(hex, metal, roughness), parent);
  }
  function cylinder(name, radius, height, pos, hex, parent, topRadius = radius) {
    return finish(CreateCylinder(name, { diameterTop: topRadius * 2, diameterBottom: radius * 2, height, tessellation: 32 }, scene), pos, material(hex, 0.7, 0.3), parent);
  }
  function sphere(name, radius, pos, parent) {
    return finish(CreateSphere(name, { diameter: radius * 2, segments: 16 }, scene), pos, material(0x596571, 0.75, 0.28), parent);
  }
  function group(name, pos = [0, 0, 0], parent) {
    const node = new TransformNode(name, scene);
    node.position.copyFromFloats(...pos);
    node.parent = parent || null;
    return node;
  }
  function arm(name, end, radius, parent) {
    const direction = new Vector3(...end);
    const mesh = cylinder(name, radius * 1.15, direction.length(), end.map(v => v / 2), 0xe8a126, parent, radius);
    const up = Vector3.Up();
    direction.normalize();
    const axis = Vector3.Cross(up, direction);
    mesh.rotationQuaternion = axis.length() < 0.00001 ? Quaternion.Identity()
      : Quaternion.RotationAxis(axis.normalize(), Math.acos(Math.max(-1, Math.min(1, Vector3.Dot(up, direction)))));
    return mesh;
  }

  const floor = CreateGround('Zemin', { width: 200, height: 200 }, scene);
  floor.position.y = -0.02;
  floor.material = material(0xf5f6f8, 0, 0.9);
  floor.receiveShadows = true;
  const lines = [];
  for (let i = -10; i <= 10; i++) {
    lines.push([new Vector3(i, -0.009, -10), new Vector3(i, -0.009, 10)]);
    lines.push([new Vector3(-10, -0.009, i), new Vector3(10, -0.009, i)]);
  }
  const grid = CreateLineSystem('Zemin ızgarası', { lines }, scene);
  grid.color = color3(0xcbd2db);

  // KONVEYÖR
  box('Konveyör bandı', [10, 0.16, 1], [0, 1.25, 0], 0x238b57);
  for (const z of [-0.56, 0.56]) box('Metal yan profil', [10, 0.18, 0.12], [0, 1.13, z], 0x87939f, 0.8);
  for (const x of [-4.5, 4.5]) for (const z of [-0.48, 0.48]) box('Şase ayağı', [0.12, 1.2, 0.12], [x, 0.62, z], 0x64717e, 0.8);
  for (const z of [-0.48, 0.48]) box('Alt uzun bağlantı', [9, 0.1, 0.1], [0, 0.25, z], 0x64717e, 0.8);
  for (const x of [-2.9, 2.9]) cylinder('Konveyör makarası', 0.13, 1.2, [x, 1.17, 0], 0x59636e).rotation.z = Math.PI / 2;
  const referenceProducts = [];
  for (let i = 0; i < 8; i++) referenceProducts.push(box(`Model ürün ${i + 1}`, [0.32, 0.28, 0.32], [-4.2 + i * 1.2, 1.47, 0], [COLORS.red, 0xf5c542, 0x2878d0][i % 3], 0.05));

  // ASANSÖRLÜ HAZNE VE İTİCİ
  const hopper = group('Hazne hareket grubu');
  box('Hazne tabanı', [1.4, 0.12, 1.4], [5.8, 1.29, 0], 0x777777, 0.2, hopper);
  box('Hazne arka duvarı', [0.12, 0.8, 1.4], [6.44, 1.75, 0], 0x999999, 0.2, hopper);
  for (const z of [-0.64, 0.64]) box('Hazne yan duvarı', [1.4, 0.8, 0.12], [5.8, 1.75, z], 0x999999, 0.2, hopper);
  for (let i = 0; i < 3; i++) referenceProducts.push(box(`Hazne model ürün ${i + 1}`, [0.32, 0.32, 0.32], [5.55, 1.53 + i * 0.34, 0], [COLORS.red, COLORS.yellow, COLORS.blue][i], 0.1, hopper));
  box('Alt kutu itici gövdesi', [0.7, 0.22, 0.55], [6.75, 1.15, 0], 0x444444, 0.3);
  const pusher = group('İtici hareket grubu');
  box('Alt kutu itici kolu', [0.65, 0.08, 0.08], [6.28, 1.33, 0], 0xaaaaaa, 0.5, pusher);
  box('Alt kutu itici plakası', [0.08, 0.3, 0.42], [5.98, 1.53, 0], 0x1565c0, 0.3, pusher);
  for (const x of [-0.55, 0.55]) for (const z of [-0.55, 0.55]) box('Hazne taşıyıcı ayağı', [0.12, 1.2, 0.12], [5.8 + x, 0.65, z], 0x555555, 0.4);
  box('Hazne alt şasesi', [1.5, 0.12, 1.5], [5.8, 0.08, 0], 0x333333, 0.5);

  // ROBOT: Dönüşler eklem merkezlerinden uygulanır; alt düğümler beraber hareket eder.
  const robot = group('Robot ray arabası', [-5.5, 0, 0]);
  cylinder('Robot tabanı', 0.48, 0.18, [0, 0.12, 0], 0x303943, robot);
  cylinder('Robot taban plakası', 0.36, 0.12, [0, 0.25, 0], 0xb8c1ca, robot);
  const base = group('Robot taban dönüşü', [0, 0, 0], robot);
  cylinder('Robot döner gövdesi', 0.28, 0.55, [0, 0.58, 0], 0xe8a126, base);
  const shoulder = group('Omuz dönüşü', [0, 0.92, 0], base);
  sphere('Omuz eklemi', 0.22, [0, 0, 0], shoulder);
  arm('Robot üst kolu', [0.48, 1.08, -0.12], 0.14, shoulder);
  const elbow = group('Dirsek dönüşü', [0.48, 1.08, -0.12], shoulder);
  sphere('Dirsek eklemi', 0.18, [0, 0, 0], elbow);
  arm('Robot ön kolu', [0.64, -0.25, 0.02], 0.105, elbow);
  const wrist = group('Bilek dönüşü', [0.64, -0.25, 0.02], elbow);
  sphere('Bilek eklemi', 0.13, [0, 0, 0], wrist);
  box('Robot bilek bağlantısı', [0.22, 0.13, 0.13], [0.12, -0.04, 0], 0x303943, 0.65, wrist);
  box('Kavrayıcı merkezi', [0.16, 0.13, 0.16], [0.25, -0.1, 0], 0x687580, 0.65, wrist);
  const fingers = [-1, 1].map(side => box(`Kavrayıcı parmak ${side}`, [0.08, 0.24, 0.07], [0.33, -0.26, side * 0.08], 0x303943, 0.65, wrist));
  const tool = group('Tutulan ürün merkezi', [0.33, -0.38, 0], wrist);

  // KAYNAK DOSYADAKİ RAY SİSTEMİ
  const rails = group('Ray sistemi', [-4, 0, 5]);
  rails.rotation.y = -Math.PI / 2;
  for (const dz of [-0.35, 0, 0.35]) cylinder('Robot rayı', 0.055, 5.5, [-2.75, 0.3, 1.5 + dz], 0x87939e, rails).rotation.z = Math.PI / 2;
  for (const x of [-5.3, -0.2]) {
    for (const dz of [-0.35, 0, 0.35]) box('Ray ayağı', [0.14, 0.6, 0.14], [x, 0, 1.5 + dz], 0x303943, 0.65, rails);
    box('Ray enine desteği', [0.18, 0.14, 1], [x, -0.2, 1.5], 0x303943, 0.65, rails);
  }

  // KARTON / BANT GİYOTİNİ
  const cutter = group('Kesim istasyonu', [-0.5, 0, 4]);
  box('Kesim tablası', [2.2, 0.12, 1.4], [0, 0.06, 0], 0x374451, 0.65, cutter);
  for (const side of [-1, 1]) box('Giyotin kolonu', [0.12, 1.5, 0.12], [side * 0.9, 0.8, 0], 0x374451, 0.65, cutter);
  box('Giyotin üst kirişi', [2, 0.16, 0.16], [0, 1.5, 0], 0x374451, 0.65, cutter);
  const blade = group('Kesici hareket grubu', [0, 1.25, 0], cutter);
  box('Kesici bıçak', [1.65, 0.07, 0.12], [0, 0, 0], 0xc4ccd3, 0.9, blade);
  box('Karton şerit', [1.9, 0.035, 0.48], [0, 0.16, 0.32], 0xc69b63, 0, cutter, 0.9);
  for (let i = -3; i <= 3; i++) box('Karton oluk çizgisi', [0.012, 0.004, 0.44], [i * 0.23, 0.18, 0.32], 0x987044, 0, cutter, 1);
  box('Sarı bant şeridi', [1.9, 0.018, 0.12], [0, 0.19, -0.28], 0xe6b82e, 0.05, cutter);
  box('Kesim çizgisi', [0.025, 0.008, 0.65], [0, 0.205, 0.02], 0xd93636, 0, cutter);
  // Kaynaktaki iç içe döngü nedeniyle üst üste çizilen masa/operatör tekilleştirildi.
  for (let row = 0; row < 2; row++) for (let level = 0; level < 3; level++) box('Ham karton kutu', [0.32, 0.8, 0.32], [1 + row * 0.38, 0.14 + level * 0.28, 4], 0xb58a5a, 0);
  box('Bantlama masası', [1.8, 0.12, 1.2], [3.5, 0.85, 4], 0x777777, 0.1);
  for (const x of [-0.75, 0.75]) for (const z of [-0.45, 0.45]) box('Masa ayağı', [0.08, 0.8, 0.08], [3.5 + x, 0.4, 4 + z], 0x444444);
  box('Bantlanacak kutu', [0.55, 0.5, 0.55], [3.5, 1.16, 4], 0xb58a5a, 0);
  box('Mavi paketleme bandı', [0.55, 0.015, 0.53], [3.5, 1.425, 4], 0x1565c0, 0);
  const operator = group('Operatör', [3.5, 0, 3.1]);
  box('Operatör gövdesi', [0.48, 0.75, 0.28], [0, 1, 0], 0x2468a0, 0, operator);
  box('Operatör başı', [0.28, 0.3, 0.28], [0, 1.6, 0], 0xd9a078, 0, operator);
  box('Operatör boynu', [0.12, 0.12, 0.12], [0, 1.44, 0], 0xd9a078, 0, operator);
  for (const side of [-1, 1]) {
    box('Operatör kolu', [0.13, 0.16, 0.3], [side * 0.24, 1.22, 0.28], 0x2468a0, 0, operator);
    box('Operatör eli', [0.11, 0.11, 0.11], [side * 0.24, 1.22, 0.43], 0xd9a078, 0, operator);
    box('Operatör bacağı', [0.18, 0.7, 0.2], [side * 0.14, 0.35, 0], 0x263746, 0, operator);
    box('Operatör ayakkabısı', [0.2, 0.1, 0.3], [side * 0.14, 0.08, 0.04], 0x222222, 0, operator);
  }

  // ÜÇ RENK KASASI + LAZER SENSÖRLERİ
  const pallets = group('Palet kasaları', [-4.2, 0, 3.5]);
  const palletProducts = { red: [], blue: [], yellow: [] };
  const livePallets = {};
  const palletSensors = {}, palletBeams = {};
  ['red', 'blue', 'yellow'].forEach((color, index) => {
    const z = (index - 1) * 1.1;
    const pallet = group(`${color} kasası`, [0.4, 0, z], pallets);
    livePallets[color] = pallet;
    box('Kasa tabanı', [1.3, 0.06, 0.95], [0, 0.03, 0], 0x657785, 0.35, pallet, 0.65);
    for (const side of [-1, 1]) {
      box('Kasa uzun duvarı', [1.3, 0.55, 0.06], [0, 0.275, side * 0.445], 0x657785, 0.35, pallet, 0.65);
      box('Kasa kısa duvarı', [0.06, 0.55, 0.95], [side * 0.62, 0.275, 0], 0x657785, 0.35, pallet, 0.65);
    }
    for (let j = 0; j < 20; j++) {
      const p = box(`${color} kasası ürün ${j + 1}`, [0.18, 0.18, 0.18], [-0.42 + j % 5 * 0.21, 0.16 + Math.floor(j / 10) * 0.2, -0.13 + Math.floor(j % 10 / 5) * 0.26], COLORS[color], 0.1, pallet);
      p.setEnabled(j < 6);
      palletProducts[color].push(p);
    }
    const sensor = group('Lazer sensörü', [1.23, 0.42, z], pallets);
    palletSensors[color]=sensor;
    sensor.rotation.y = Math.PI / 2;
    box('Lazer sensör gövdesi', [0.22, 0.16, 0.18], [0, 0, 0], 0x303840, 0.75, sensor);
    box('Lazer montaj aparatı', [0.12, 0.12, 0.12], [0, 0, -0.12], 0x87939f, 0.8, sensor);
    const lens = cylinder('Lazer lensi', 0.035, 0.025, [0, -0.025, 0.095], 0xff2020, sensor);
    lens.rotation.x = Math.PI / 2;
    const beam = cylinder('Lazer ışını', 0.025, 1.2, [0.58, 0.42, z], 0xff2020, pallets);
    palletBeams[color]=beam;
    beam.rotation.z = Math.PI / 2;
    const beamMat = new StandardMaterial(`Lazer malzemesi ${index}`, scene);
    beamMat.emissiveColor = color3(0xff2020);
    beamMat.disableLighting = true;
    beamMat.alpha = 0.65;
    beam.material = beamMat;
  });
  const sensorX = -3.25;
  for (const z of [-0.54, 0.54]) box('Renk sensörü yan duvarı', [0.65, 0.45, 0.08], [sensorX, 1.47, z], 0x555555, 0.3);
  for (const x of [-0.325, 0.325]) for (const z of [-0.39, 0.39]) box('Renk sensörü geçiş duvarı', [0.08, 0.45, 0.3], [sensorX + x, 1.47, z], 0x555555, 0.3);
  box('Renk sensörü üst kapağı', [0.65, 0.08, 1.08], [sensorX, 1.735, 0], 0x555555, 0.3);

  const dynamicProducts = new Map();
  function product(id, color = 'unknown') {
    if (!dynamicProducts.has(id)) {
      dynamicProducts.set(id, box(`Canlı ürün ${id}`, [0.32, 0.28, 0.32], [LINE_CONFIG.hopperX, 1.47, 0], COLORS[color] ?? COLORS.unknown, 0.05));
    }
    const mesh = dynamicProducts.get(id);
    mesh.material = material(COLORS[color] ?? COLORS.unknown, 0.05);
    return mesh;
  }
  const sensorMeshes = scene.meshes.filter(m => m.name.startsWith('Renk sensörü'));
  const originalSensorX = sensorMeshes.map(m => m.position.x);
  const liveRobot = group('AnyLogic canlı robot');
  const liveLinks = Array.from({length:7}, (_,i) => cylinder(`AnyLogic robot kolu ${i+1}`, .12, 1, [0,0,0], i%2 ? 0x303943 : 0xe8a126, liveRobot));
  const liveJoints = Array.from({length:7}, (_,i) => sphere(`AnyLogic robot eklemi ${i+1}`, .2, [0,0,0], liveRobot));
  liveRobot.setEnabled(false);
  function setLiveLayout(layout, map) {
    robot.setEnabled(false); liveRobot.setEnabled(true);
    sensorMeshes.forEach((m,i) => {m.position.x=originalSensorX[i]+5.55-layout.cameraProgress*9.6-sensorX;});
    for (const [color,node] of Object.entries(livePallets)) {
      const p=map(layout.drops[color],layout);
      node.position.set(p[0]-pallets.position.x,0,p[2]-pallets.position.z);
      palletSensors[color].position.set(node.position.x+.83,.42,node.position.z);
      palletBeams[color].position.set(node.position.x+.18,.42,node.position.z);
    }
  }
  function setLiveRobot(points) {
    points.forEach((p,i) => {
      if(i<liveJoints.length)liveJoints[i].position.copyFromFloats(...p);
      if(i===0)return;
      const a=new Vector3(...points[i-1]),b=new Vector3(...p),direction=b.subtract(a);
      const link=liveLinks[i-1];
      link.position.copyFrom(a.add(b).scale(.5)); link.scaling.y=Math.max(.001,direction.length());
      link.rotationQuaternion=Quaternion.FromUnitVectorsToRef(Vector3.Up(),direction.normalize(),new Quaternion());
    });
  }
  function setPalletCount(color, count, capacity=LINE_CONFIG.capacity) {
    palletProducts[color]?.forEach((p, i) => p.setEnabled(i < Math.max(0, Math.min(capacity, count))));
  }
  function reset(model = false) {
    for (const mesh of dynamicProducts.values()) mesh.dispose();
    dynamicProducts.clear();
    robot.setEnabled(true); liveRobot.setEnabled(false);
    sensorMeshes.forEach((m,i)=>{m.position.x=originalSensorX[i];});
    Object.values(livePallets).forEach((p,i)=>p.position.set(.4,0,(i-1)*1.1));
    Object.values(palletSensors).forEach((p,i)=>p.position.set(1.23,.42,(i-1)*1.1));
    Object.values(palletBeams).forEach((p,i)=>p.position.set(.58,.42,(i-1)*1.1));
    referenceProducts.forEach(p => p.setEnabled(model));
    for (const c of Object.keys(palletProducts)) setPalletCount(c, model ? 6 : 0);
    robot.position.set(-5.5, 0, 0);
    base.rotation.set(0, 0, 0);
    shoulder.rotation.set(0, 0, 0);
    elbow.rotation.set(0, 0, 0);
    wrist.rotation.set(0, 0, 0);
    fingers.forEach((f, i) => { f.position.z = (i === 0 ? -1 : 1) * 0.08; });
    blade.position.y = 1.25;
    hopper.position.y = 0;
    pusher.position.x = 0;
  }
  function view(name) {
    const views = { overview: [9, 7, 12], front: [0, 6, 19], top: [0, 20, 2.01], robot: [-10, 5, 8] };
    camera.setTarget(new Vector3(name === 'robot' ? -4 : 0, 1, 2));
    camera.setPosition(new Vector3(...(views[name] || views.overview)));
    if (name === 'overview') {
      const aspect=engine.getRenderWidth()/Math.max(1,engine.getRenderHeight());
      camera.radius=Math.max(camera.radius,24/Math.min(1,Math.max(.7,aspect)));
    }
  }
  return { scene, camera, robot, base, shoulder, elbow, wrist, tool, fingers, blade, hopper, pusher, product, dynamicProducts, setPalletCount, setLiveLayout, setLiveRobot, reset, view };
}
