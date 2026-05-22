import { useRef, useEffect, useCallback } from 'react';

interface Props {
  imageUrl: string;
  isSpeaking: boolean;
  size?: number;
}

/**
 * VideoAvatar —— 照片驱动的数字人动画（纯Canvas 2D，无需GPU）
 *
 * 在普通电脑上实现"他在看我、在说话"的错觉：
 * 1. 呼吸：轻微缩放（正弦波）
 * 2. 眨眼：随机间隔，快速闭眼再睁开
 * 3. 嘴型：根据 isSpeaking 开口/闭口
 * 4. 眼神：轻微跟随鼠标（让眼睛有焦点感）
 * 5. 微晃动：头部轻微左右摆动
 */
export function VideoAvatar({ imageUrl, isSpeaking, size = 320 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const stateRef = useRef({
    time: 0,
    blinkState: 0, // 0=open, 1=closing, 2=closed, 3=opening
    blinkTimer: 0,
    nextBlink: 200 + Math.random() * 300, // frames until next blink
    mouthOpen: 0,
    mouseX: 0.5,
    mouseY: 0.5,
    headOffsetX: 0,
    headOffsetY: 0,
    loaded: false,
  });

  // 加载图片
  useEffect(() => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      imgRef.current = img;
      stateRef.current.loaded = true;
    };
    img.src = imageUrl;
  }, [imageUrl]);

  // 跟踪鼠标位置（用于眼神）
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      stateRef.current.mouseX = e.clientX / window.innerWidth;
      stateRef.current.mouseY = e.clientY / window.innerHeight;
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img || !stateRef.current.loaded) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const s = stateRef.current;
    s.time += 1;

    // 画布尺寸
    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;

    // 1. 呼吸：轻微缩放（周期 4 秒）
    const breath = 1 + Math.sin(s.time * 0.015) * 0.008;

    // 2. 头部微晃动（周期 6 秒和 8 秒叠加）
    s.headOffsetX = Math.sin(s.time * 0.008) * 2 + Math.sin(s.time * 0.013) * 1;
    s.headOffsetY = Math.cos(s.time * 0.01) * 1.5;

    // 3. 眨眼逻辑
    s.blinkTimer += 1;
    if (s.blinkState === 0 && s.blinkTimer > s.nextBlink) {
      s.blinkState = 1; // start closing
      s.blinkTimer = 0;
    } else if (s.blinkState === 1 && s.blinkTimer > 3) {
      s.blinkState = 2; // closed
      s.blinkTimer = 0;
    } else if (s.blinkState === 2 && s.blinkTimer > 2) {
      s.blinkState = 3; // opening
      s.blinkTimer = 0;
    } else if (s.blinkState === 3 && s.blinkTimer > 3) {
      s.blinkState = 0; // open
      s.blinkTimer = 0;
      s.nextBlink = 180 + Math.random() * 250; // 3-7秒随机眨眼
    }

    // 眨眼程度：0=全开, 1=全闭
    let eyeClosed = 0;
    if (s.blinkState === 1) eyeClosed = s.blinkTimer / 3;
    else if (s.blinkState === 2) eyeClosed = 1;
    else if (s.blinkState === 3) eyeClosed = 1 - s.blinkTimer / 3;

    // 4. 嘴型：说话时开口
    const targetMouth = isSpeaking ? 0.3 + Math.sin(s.time * 0.25) * 0.15 : 0;
    s.mouthOpen += (targetMouth - s.mouthOpen) * 0.3; // 平滑过渡

    // 清空画布
    ctx.clearRect(0, 0, w, h);

    ctx.save();

    // 移动到中心，应用呼吸缩放和头部晃动
    ctx.translate(cx + s.headOffsetX, cy + s.headOffsetY);
    ctx.scale(breath, breath);

    // 绘制圆形裁剪区域（头像）
    const r = Math.min(w, h) * 0.45;
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.clip();

    // 绘制照片
    const imgSize = r * 2.2;
    ctx.drawImage(img, -imgSize / 2, -imgSize / 2, imgSize, imgSize);

    // 5. 眼神偏移（看向鼠标方向）
    const gazeX = (s.mouseX - 0.5) * 4; // -2 ~ +2 px
    const gazeY = (s.mouseY - 0.5) * 3;

    // 眼睛区域（大约在脸部上半部分）
    const eyeY = -r * 0.1;
    const eyeSpacing = r * 0.35;
    const eyeW = r * 0.18;
    const eyeH = r * 0.08;

    // 左眼
    ctx.save();
    ctx.translate(-eyeSpacing + gazeX, eyeY + gazeY);
    ctx.beginPath();
    ctx.ellipse(0, 0, eyeW, eyeH * (1 - eyeClosed * 0.9), 0, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(255, 255, 255, ${0.1 + eyeClosed * 0.3})`;
    ctx.fill();
    ctx.restore();

    // 右眼
    ctx.save();
    ctx.translate(eyeSpacing + gazeX, eyeY + gazeY);
    ctx.beginPath();
    ctx.ellipse(0, 0, eyeW, eyeH * (1 - eyeClosed * 0.9), 0, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(255, 255, 255, ${0.1 + eyeClosed * 0.3})`;
    ctx.fill();
    ctx.restore();

    // 6. 嘴型（说话时的开口）
    if (s.mouthOpen > 0.01) {
      const mouthY = r * 0.25;
      const mouthW = r * 0.2;
      const mouthH = r * 0.15 * s.mouthOpen;

      ctx.save();
      ctx.beginPath();
      ctx.ellipse(0, mouthY, mouthW, mouthH, 0, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(80, 20, 20, 0.6)';
      ctx.fill();
      // 嘴唇高光
      ctx.beginPath();
      ctx.ellipse(0, mouthY - mouthH * 0.3, mouthW * 0.8, mouthH * 0.3, 0, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(200, 120, 120, 0.3)';
      ctx.fill();
      ctx.restore();
    }

    // 7. 面部阴影（增加立体感）
    const shadowGrad = ctx.createRadialGradient(0, 0, r * 0.6, 0, 0, r);
    shadowGrad.addColorStop(0, 'rgba(0,0,0,0)');
    shadowGrad.addColorStop(1, 'rgba(0,0,0,0.3)');
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.fillStyle = shadowGrad;
    ctx.fill();

    ctx.restore();

    // 8. 外发光（通话中）
    if (isSpeaking) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, r + 4 + Math.sin(s.time * 0.2) * 2, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(7, 193, 96, ${0.3 + Math.sin(s.time * 0.15) * 0.1})`;
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.restore();
    }

    requestAnimationFrame(draw);
  }, [isSpeaking]);

  useEffect(() => {
    let raf: number;
    const loop = () => {
      draw();
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [draw]);

  return (
    <canvas
      ref={canvasRef}
      width={size}
      height={size}
      className="rounded-full"
      style={{ width: size, height: size }}
    />
  );
}
