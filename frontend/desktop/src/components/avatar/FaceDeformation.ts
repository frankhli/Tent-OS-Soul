/**
 * 面部变形系统 — 参数化表情
 * 借鉴 Live2D：任何表情都是一组参数的组合
 */

export interface FaceParams {
  // 眉毛
  browLHeight: number;   // -1~1, 负=下垂, 正=扬起
  browLAngle: number;    // -1~1, 负=外侧下压(生气), 正=外侧上扬(开心)
  browRHeight: number;
  browRAngle: number;

  // 眼睛
  eyeLOpen: number;      // 0~1
  eyeROpen: number;
  eyeLPupil: number;     // 0~1, 瞳孔缩放
  eyeRPupil: number;
  eyeLSquint: number;    // 0~1, 眯眼程度
  eyeRSquint: number;

  // 嘴巴
  mouthWidth: number;    // 0~1
  mouthHeight: number;   // -1~1, 负=撅嘴, 正=张嘴
  mouthCurve: number;    // -1~1, 负=下垂, 正=上扬
  mouthOpen: number;     // 0~1, 口腔开合

  // 脸颊
  cheekBlush: number;    // 0~1
  cheekPuff: number;     // 0~1, 鼓起(生气/嘟嘴)

  // 整体
  faceTilt: number;      // -1~1, 头部倾斜
  faceSquash: number;    // 0~1, 挤压(惊讶/害怕)

  // 扩展：眼泪
  tearL: number;         // 0~1, 左眼眼泪
  tearR: number;         // 0~1, 右眼眼泪

  // 扩展：星星眼
  starEyes: number;      // 0~1, 星星眼程度

  // 扩展：表情不对称（真实人脸左右不完全对称）
  asymmetry: number;     // 0~1, 整体不对称程度
  browAsymmetry: number; // -1~1, 眉毛额外不对称偏移
  eyeAsymmetry: number;  // -1~1, 眼睛额外不对称
}

export const DEFAULT_FACE: FaceParams = {
  browLHeight: 0, browLAngle: 0, browRHeight: 0, browRAngle: 0,
  eyeLOpen: 1, eyeROpen: 1, eyeLPupil: 0.5, eyeRPupil: 0.5,
  eyeLSquint: 0, eyeRSquint: 0,
  mouthWidth: 0.5, mouthHeight: 0, mouthCurve: 0, mouthOpen: 0,
  cheekBlush: 0, cheekPuff: 0,
  faceTilt: 0, faceSquash: 0,
  tearL: 0, tearR: 0,
  starEyes: 0,
  asymmetry: 0.1, browAsymmetry: 0, eyeAsymmetry: 0,
};

/** 表情预设 */
export const FACE_PRESETS: Record<string, Partial<FaceParams>> = {
  neutral: {},

  happy: {
    browLHeight: 0.3, browLAngle: 0.4, browRHeight: 0.3, browRAngle: 0.4,
    eyeLOpen: 0.9, eyeROpen: 0.9, eyeLPupil: 0.7, eyeRPupil: 0.7,
    mouthWidth: 0.8, mouthHeight: 0.2, mouthCurve: 0.8, mouthOpen: 0.3,
    cheekBlush: 0.3,
  },

  excited: {
    browLHeight: 0.6, browLAngle: 0.5, browRHeight: 0.6, browRAngle: 0.5,
    eyeLOpen: 1, eyeROpen: 1, eyeLPupil: 0.9, eyeRPupil: 0.9,
    mouthWidth: 0.9, mouthHeight: 0.4, mouthCurve: 0.9, mouthOpen: 0.5,
    cheekBlush: 0.5, faceSquash: 0.2,
  },

  sad: {
    browLHeight: -0.4, browLAngle: -0.3, browRHeight: -0.4, browRAngle: -0.3,
    eyeLOpen: 0.6, eyeROpen: 0.6, eyeLPupil: 0.4, eyeRPupil: 0.4,
    mouthWidth: 0.4, mouthHeight: -0.2, mouthCurve: -0.5, mouthOpen: 0,
    cheekBlush: 0.2, faceTilt: 0.1,
  },

  angry: {
    browLHeight: -0.5, browLAngle: -0.6, browRHeight: -0.5, browRAngle: -0.6,
    eyeLOpen: 0.6, eyeROpen: 0.6, eyeLPupil: 0.3, eyeRPupil: 0.3,
    eyeLSquint: 0.4, eyeRSquint: 0.4,
    mouthWidth: 0.7, mouthHeight: -0.1, mouthCurve: -0.3, mouthOpen: 0.1,
    cheekPuff: 0.3, faceSquash: 0.1,
  },

  surprised: {
    browLHeight: 0.8, browLAngle: 0.2, browRHeight: 0.8, browRAngle: 0.2,
    eyeLOpen: 1, eyeROpen: 1, eyeLPupil: 0.9, eyeRPupil: 0.9,
    mouthWidth: 0.6, mouthHeight: 0.6, mouthCurve: 0, mouthOpen: 0.7,
    faceSquash: 0.3,
  },

  thinking: {
    browLHeight: -0.1, browLAngle: 0.1, browRHeight: -0.2, browRAngle: 0.3,
    eyeLOpen: 0.5, eyeROpen: 0.5, eyeLPupil: 0.4, eyeRPupil: 0.4,
    eyeLSquint: 0.2, eyeRSquint: 0.3,
    mouthWidth: 0.3, mouthHeight: 0, mouthCurve: 0, mouthOpen: 0,
    faceTilt: 0.2,
  },

  sleepy: {
    browLHeight: -0.1, browLAngle: 0, browRHeight: -0.1, browRAngle: 0,
    eyeLOpen: 0.15, eyeROpen: 0.15, eyeLPupil: 0.3, eyeRPupil: 0.3,
    mouthWidth: 0.3, mouthHeight: 0, mouthCurve: 0, mouthOpen: 0,
    faceTilt: 0.1,
  },

  shy: {
    browLHeight: 0.2, browLAngle: 0.3, browRHeight: 0.2, browRAngle: 0.3,
    eyeLOpen: 0.5, eyeROpen: 0.5, eyeLPupil: 0.4, eyeRPupil: 0.4,
    eyeLSquint: 0.1, eyeRSquint: 0.1,
    mouthWidth: 0.4, mouthHeight: -0.1, mouthCurve: 0.3, mouthOpen: 0,
    cheekBlush: 0.7, faceTilt: -0.1,
  },

  worried: {
    browLHeight: -0.2, browLAngle: -0.5, browRHeight: -0.3, browRAngle: -0.4,
    eyeLOpen: 0.6, eyeROpen: 0.6, eyeLPupil: 0.4, eyeRPupil: 0.4,
    mouthWidth: 0.3, mouthHeight: -0.1, mouthCurve: -0.3, mouthOpen: 0,
    faceTilt: 0.1,
    tearL: 0.1, tearR: 0.15,
  },

  embarrassed: {
    browLHeight: 0.1, browLAngle: -0.2, browRHeight: 0.1, browRAngle: -0.2,
    eyeLOpen: 0.5, eyeROpen: 0.5, eyeLPupil: 0.3, eyeRPupil: 0.3,
    eyeLSquint: 0.1, eyeRSquint: 0.1,
    mouthWidth: 0.4, mouthHeight: -0.1, mouthCurve: 0.1, mouthOpen: 0,
    cheekBlush: 0.8, faceTilt: -0.1,
  },

  crying: {
    browLHeight: -0.3, browLAngle: -0.4, browRHeight: -0.3, browRAngle: -0.4,
    eyeLOpen: 0.7, eyeROpen: 0.7, eyeLPupil: 0.4, eyeRPupil: 0.4,
    mouthWidth: 0.5, mouthHeight: -0.2, mouthCurve: -0.6, mouthOpen: 0.1,
    cheekBlush: 0.3, faceTilt: 0.15,
    tearL: 0.8, tearR: 0.8,
  },

  love: {
    browLHeight: 0.4, browLAngle: 0.3, browRHeight: 0.4, browRAngle: 0.3,
    eyeLOpen: 0.8, eyeROpen: 0.8, eyeLPupil: 0.6, eyeRPupil: 0.6,
    mouthWidth: 0.6, mouthHeight: 0.1, mouthCurve: 0.7, mouthOpen: 0.2,
    cheekBlush: 0.9,
    starEyes: 0.6,
  },
};

/** 根据情绪标签获取面部参数 */
export function getFaceForEmotion(emotion: string): FaceParams {
  const preset = FACE_PRESETS[emotion] || FACE_PRESETS.neutral || {};
  return { ...DEFAULT_FACE, ...preset };
}

/** 两个表情之间插值 */
export function lerpFace(a: FaceParams, b: FaceParams, t: number): FaceParams {
  const lerp = (x: number, y: number) => x + (y - x) * t;
  return {
    browLHeight: lerp(a.browLHeight, b.browLHeight),
    browLAngle: lerp(a.browLAngle, b.browLAngle),
    browRHeight: lerp(a.browRHeight, b.browRHeight),
    browRAngle: lerp(a.browRAngle, b.browRAngle),
    eyeLOpen: lerp(a.eyeLOpen, b.eyeLOpen),
    eyeROpen: lerp(a.eyeROpen, b.eyeROpen),
    eyeLPupil: lerp(a.eyeLPupil, b.eyeLPupil),
    eyeRPupil: lerp(a.eyeRPupil, b.eyeRPupil),
    eyeLSquint: lerp(a.eyeLSquint, b.eyeLSquint),
    eyeRSquint: lerp(a.eyeRSquint, b.eyeRSquint),
    mouthWidth: lerp(a.mouthWidth, b.mouthWidth),
    mouthHeight: lerp(a.mouthHeight, b.mouthHeight),
    mouthCurve: lerp(a.mouthCurve, b.mouthCurve),
    mouthOpen: lerp(a.mouthOpen, b.mouthOpen),
    cheekBlush: lerp(a.cheekBlush, b.cheekBlush),
    cheekPuff: lerp(a.cheekPuff, b.cheekPuff),
    faceTilt: lerp(a.faceTilt, b.faceTilt),
    faceSquash: lerp(a.faceSquash, b.faceSquash),
    tearL: lerp(a.tearL, b.tearL),
    tearR: lerp(a.tearR, b.tearR),
    starEyes: lerp(a.starEyes, b.starEyes),
    asymmetry: lerp(a.asymmetry, b.asymmetry),
    browAsymmetry: lerp(a.browAsymmetry, b.browAsymmetry),
    eyeAsymmetry: lerp(a.eyeAsymmetry, b.eyeAsymmetry),
  };
}

/** 应用表情不对称（让表情更真实） */
export function applyAsymmetry(face: FaceParams, time: number): FaceParams {
  const f = { ...face };
  const asym = f.asymmetry || 0.1;
  
  // 基础不对称：左右眉毛/眼睛天然有微小差异
  const baseOffset = Math.sin(time * 0.7) * 0.02 * asym;
  f.browLHeight += baseOffset;
  f.browRHeight -= baseOffset * 0.8;
  
  // 额外的场景不对称
  const extraAsym = Math.sin(time * 1.3 + 1) * 0.03 * asym;
  f.browLHeight += extraAsym + f.browAsymmetry * 0.1;
  f.browRHeight -= extraAsym * 0.6 + f.browAsymmetry * 0.05;
  
  // 眼睛不对称
  f.eyeLOpen += Math.sin(time * 0.9) * 0.015 * asym + f.eyeAsymmetry * 0.05;
  f.eyeROpen += Math.cos(time * 0.8) * 0.01 * asym - f.eyeAsymmetry * 0.03;
  
  return f;
}

/** 根据连续情感维度生成面部参数 */
export function faceFromEmotionVector(valence: number, arousal: number, dominance: number): FaceParams {
  const face: FaceParams = { ...DEFAULT_FACE };

  // valence → 嘴巴弧度 + 眉毛高度
  face.mouthCurve = valence * 0.8;
  face.browLHeight = valence * 0.5;
  face.browRHeight = valence * 0.5;

  // arousal → 眼睛睁开 + 瞳孔大小
  face.eyeLOpen = 0.4 + arousal * 0.6;
  face.eyeROpen = 0.4 + arousal * 0.6;
  face.eyeLPupil = 0.3 + arousal * 0.5;
  face.eyeRPupil = 0.3 + arousal * 0.5;

  // dominance → 眉毛角度 + 眯眼
  face.browLAngle = -dominance * 0.4;
  face.browRAngle = -dominance * 0.4;
  face.eyeLSquint = (1 - dominance) * 0.3;
  face.eyeRSquint = (1 - dominance) * 0.3;

  // 极端 valence
  if (valence > 0.5) {
    face.cheekBlush = (valence - 0.5) * 0.8;
    face.mouthWidth = 0.5 + valence * 0.4;
    face.starEyes = (valence - 0.6) * 0.8;
  } else if (valence < -0.3) {
    face.mouthWidth = 0.5 + valence * 0.2;
    face.mouthHeight = valence * 0.3;
    face.tearL = (-valence - 0.3) * 0.6;
    face.tearR = (-valence - 0.3) * 0.55; // 右眼眼泪略少，不对称
  }

  // 天然不对称
  face.asymmetry = 0.15;

  return face;
}
