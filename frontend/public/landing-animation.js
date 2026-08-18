(function() {
  const canvas = document.createElement('canvas');
  canvas.id = 'landing-bg-canvas';
  canvas.style.position = 'absolute';
  canvas.style.top = '0';
  canvas.style.left = '0';
  canvas.style.width = '100%';
  canvas.style.height = '100%';
  canvas.style.zIndex = '0';
  canvas.style.pointerEvents = 'none';
  
  const target = document.querySelector('.landing-hero-section') || document.getElementById('landing-page');
  if (target) {
    target.style.position = 'relative';
    target.insertBefore(canvas, target.firstChild);
  } else {
    document.body.appendChild(canvas);
  }

  const ctx = canvas.getContext('2d');
  let width = canvas.width = target ? target.offsetWidth : window.innerWidth;
  let height = canvas.height = target ? target.offsetHeight : window.innerHeight;

  const mouse = { x: null, y: null, radius: 250 };
  const gridSize = 60;
  
  // Data packets traversing the grid lines
  const packets = [];
  const maxPackets = 18;

  function updateDimensions() {
    if (target) {
      width = canvas.width = target.offsetWidth;
      height = canvas.height = target.offsetHeight;
    } else {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    }
  }

  window.addEventListener('resize', updateDimensions);

  window.addEventListener('mousemove', (e) => {
    if (!target) return;
    const rect = target.getBoundingClientRect();
    mouse.x = e.clientX - rect.left;
    mouse.y = e.clientY - rect.top;
  });

  window.addEventListener('mouseleave', () => {
    mouse.x = null;
    mouse.y = null;
  });

  class DataPacket {
    constructor() {
      this.reset();
    }

    reset() {
      // Align start point strictly to grid coordinates
      this.gridX = Math.floor(Math.random() * (width / gridSize)) * gridSize;
      this.gridY = Math.floor(Math.random() * (height / gridSize)) * gridSize;
      this.x = this.gridX;
      this.y = this.gridY;
      this.speed = Math.random() * 1.5 + 0.8;
      this.length = Math.floor(Math.random() * 15) + 8;
      
      // Random direction: 0 = Right, 1 = Left, 2 = Down, 3 = Up
      this.direction = Math.floor(Math.random() * 4);
      this.progress = 0;
      this.active = true;
    }

    update() {
      if (!this.active) return;

      this.progress += this.speed;
      if (this.progress >= gridSize) {
        // Snap to next grid intersection
        if (this.direction === 0) this.gridX += gridSize;
        else if (this.direction === 1) this.gridX -= gridSize;
        else if (this.direction === 2) this.gridY += gridSize;
        else if (this.direction === 3) this.gridY -= gridSize;

        this.x = this.gridX;
        this.y = this.gridY;
        this.progress = 0;

        // Choose next random direction, keeping inside viewport boundary
        const choices = [];
        if (this.gridX + gridSize < width) choices.push(0);
        if (this.gridX - gridSize > 0) choices.push(1);
        if (this.gridY + gridSize < height) choices.push(2);
        if (this.gridY - gridSize > 0) choices.push(3);

        if (choices.length > 0 && Math.random() > 0.08) {
          this.direction = choices[Math.floor(Math.random() * choices.length)];
        } else {
          this.reset();
        }
      } else {
        // Travel towards direction
        if (this.direction === 0) this.x = this.gridX + this.progress;
        else if (this.direction === 1) this.x = this.gridX - this.progress;
        else if (this.direction === 2) this.y = this.gridY + this.progress;
        else if (this.direction === 3) this.y = this.gridY - this.progress;
      }

      // Deactivate if out of bounds
      if (this.x < -100 || this.x > width + 100 || this.y < -100 || this.y > height + 100) {
        this.reset();
      }
    }

    draw(isDark) {
      ctx.beginPath();
      // Flow gradient along packet length
      const color = isDark ? 'rgba(34, 197, 94, 0.45)' : 'rgba(34, 197, 94, 0.28)';
      ctx.fillStyle = color;
      ctx.arc(this.x, this.y, 1.8, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // Populate data packets
  for (let i = 0; i < maxPackets; i++) {
    packets.push(new DataPacket());
  }

  // Pulsing helper variables
  let pulseTime = 0;

  function animate() {
    ctx.clearRect(0, 0, width, height);
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

    // Draw architectural subtle grid lines
    ctx.lineWidth = 0.75;
    ctx.strokeStyle = isDark ? 'rgba(255, 255, 255, 0.03)' : 'rgba(15, 23, 42, 0.03)';
    
    // Vertical grid lines
    for (let x = 0; x < width; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }

    // Horizontal grid lines
    for (let y = 0; y < height; y += gridSize) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // Draw micro grid intersection dots
    ctx.fillStyle = isDark ? 'rgba(16, 185, 129, 0.2)' : 'rgba(16, 185, 129, 0.15)';
    for (let x = 0; x < width; x += gridSize * 2) {
      for (let y = 0; y < height; y += gridSize * 2) {
        ctx.beginPath();
        ctx.arc(x, y, 1.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // Update and draw subtle grid data packets
    for (let i = 0; i < packets.length; i++) {
      packets[i].update();
      packets[i].draw(isDark);
    }

    requestAnimationFrame(animate);
  }

  animate();
})();
