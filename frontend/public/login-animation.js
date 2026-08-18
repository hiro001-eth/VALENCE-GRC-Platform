(function initLoginAnimation() {
  function start() {
    const container = document.getElementById('login-animation-root');
    if (!container) return;

    container.innerHTML = '';
    const canvas = document.createElement('canvas');
    canvas.style.display = 'block';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.opacity = '0.7';
    container.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    let animationFrameId;
    let width = window.innerWidth;
    let height = window.innerHeight;

    const numNodes = 35;
    const maxDistance = 150;
    const nodes = [];
    const labels = ['SOC Alert', 'GRC Sync', 'Risk Model', 'Compliance', 'Audit Trail', 'Threat Intel', 'Data Feed', 'Monitor'];

    const resizeCanvas = () => {
      const parent = container.parentElement;
      width = (parent && parent.clientWidth > 0) ? parent.clientWidth : Math.floor(window.innerWidth * 0.5);
      height = (parent && parent.clientHeight > 0) ? parent.clientHeight : window.innerHeight;
      canvas.width = width;
      canvas.height = height;

      if (nodes.length > 0 && (nodes[0].x === 0 || nodes[0].x > width) && width > 0) {
        for (let i = 0; i < nodes.length; i++) {
          nodes[i].x = Math.random() * width;
          nodes[i].y = Math.random() * height;
        }
      }
    };

    for (let i = 0; i < numNodes; i++) {
      nodes.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        radius: Math.random() * 2 + 1.5,
        baseRadius: Math.random() * 2 + 1.5,
        label: Math.random() > 0.8 ? labels[Math.floor(Math.random() * labels.length)] : null,
        pulse: Math.random() * Math.PI * 2,
        pulseSpeed: 0.02 + Math.random() * 0.05
      });
    }

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    const packets = [];

    function draw() {
      ctx.fillStyle = 'rgba(26, 28, 32, 0.3)';
      ctx.fillRect(0, 0, width, height);

      nodes.forEach(node => {
        node.x += node.vx;
        node.y += node.vy;

        if (node.x < 0 || node.x > width) node.vx *= -1;
        if (node.y < 0 || node.y > height) node.vy *= -1;

        node.pulse += node.pulseSpeed;
        node.radius = node.baseRadius + Math.sin(node.pulse) * 0.5;
      });

      ctx.lineWidth = 0.8;
      for (let i = 0; i < numNodes; i++) {
        for (let j = i + 1; j < numNodes; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < maxDistance) {
            const opacity = 1 - (dist / maxDistance);
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.strokeStyle = `rgba(61, 155, 147, ${opacity * 0.4})`;
            ctx.stroke();

            if (Math.random() < 0.001) {
              packets.push({
                start: nodes[i],
                end: nodes[j],
                progress: 0,
                speed: 0.01 + Math.random() * 0.02
              });
            }
          }
        }
      }

      for (let i = packets.length - 1; i >= 0; i--) {
        const p = packets[i];
        p.progress += p.speed;
        if (p.progress >= 1) {
          packets.splice(i, 1);
          continue;
        }
        const currentX = p.start.x + (p.end.x - p.start.x) * p.progress;
        const currentY = p.start.y + (p.end.y - p.start.y) * p.progress;
        ctx.beginPath();
        ctx.arc(currentX, currentY, 2, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(16, 185, 129, 0.4)';
        ctx.fill();
      }

      nodes.forEach(node => {
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
        ctx.fillStyle = node.label ? '#10B981' : '#059669';
        ctx.fill();

        if (node.label) {
          ctx.font = "10px 'Inter', sans-serif";
          ctx.fillStyle = `rgba(148, 163, 184, ${Math.abs(Math.sin(node.pulse)) * 0.5 + 0.5})`;
          ctx.fillText(node.label, node.x + 8, node.y - 8);
        }
      });

      animationFrameId = window.requestAnimationFrame(draw);
    }

    draw();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
