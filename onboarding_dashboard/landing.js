/* ============================================================
   Agent2Pay Landing Page — Animations & Interactions
   ============================================================ */

(function () {
  "use strict";

  /* --- Scroll Reveal (IntersectionObserver) --- */
  const bindRevealAnimations = () => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in-view");
          }
        }
      },
      { threshold: 0.1, rootMargin: "0px 0px 0px 0px" }
    );

    for (const el of document.querySelectorAll(".reveal")) {
      observer.observe(el);
    }
  };

  /* --- Navbar scroll effect --- */
  const bindNavbarScroll = () => {
    const navbar = document.getElementById("navbar");
    if (!navbar) return;

    let ticking = false;
    const onScroll = () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          navbar.classList.toggle("is-scrolled", window.scrollY > 40);
          ticking = false;
        });
        ticking = true;
      }
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  };

  /* --- Typing Effect for Voice Demo --- */
  const bindTypingEffect = () => {
    const text1El = document.getElementById("voice-text-1");
    const cursor1 = document.getElementById("cursor-1");
    const line2 = document.getElementById("voice-line-2");
    const text2El = document.getElementById("voice-text-2");
    const line3 = document.getElementById("voice-line-3");
    const text3El = document.getElementById("voice-text-3");

    if (!text1El || !line2 || !text2El || !line3 || !text3El) return;

    const phrases = [
      { text: '"Pay 50 AED to Sarah"', el: text1El, line: null, cursor: cursor1 },
      { text: "Understood. Sending 50 AED to Sarah. Confirm?", el: text2El, line: line2, cursor: null },
      { text: "Payment confirmed. Transaction complete.", el: text3El, line: line3, cursor: null },
    ];

    let running = false;

    const typeText = (text, el, speed) => {
      return new Promise((resolve) => {
        let i = 0;
        el.textContent = "";
        const interval = setInterval(() => {
          el.textContent += text[i];
          i++;
          if (i >= text.length) {
            clearInterval(interval);
            resolve();
          }
        }, speed);
      });
    };

    const runSequence = async () => {
      if (running) return;
      running = true;

      // Reset
      text1El.textContent = "";
      text2El.textContent = "";
      text3El.textContent = "";
      line2.style.opacity = "0";
      line3.style.opacity = "0";
      if (cursor1) cursor1.style.display = "inline-block";

      // Type user command
      await typeText(phrases[0].text, phrases[0].el, 55);
      if (cursor1) cursor1.style.display = "none";

      await sleep(600);

      // AI response
      line2.style.opacity = "1";
      line2.style.transition = "opacity 0.4s ease";
      await typeText(phrases[1].text, phrases[1].el, 30);

      await sleep(800);

      // Status
      line3.style.opacity = "1";
      line3.style.transition = "opacity 0.4s ease";
      await typeText(phrases[2].text, phrases[2].el, 30);

      await sleep(3000);

      running = false;
      // Loop
      runSequence();
    };

    // Start when visible
    const voiceSection = document.getElementById("feature-voice");
    if (!voiceSection) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && !running) {
            runSequence();
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.3 }
    );

    observer.observe(voiceSection);
  };

  /* --- Security Steps Animation --- */
  const bindSecurityAnimation = () => {
    const demo = document.getElementById("security-demo");
    if (!demo) return;

    const steps = demo.querySelectorAll(".security-step");
    if (steps.length === 0) return;

    let currentStep = 0;
    let animating = false;

    const animateSteps = () => {
      if (animating) return;
      animating = true;

      const interval = setInterval(() => {
        if (currentStep < steps.length) {
          steps[currentStep].classList.add("is-active");
          currentStep++;
        } else {
          clearInterval(interval);
          // Reset after pause
          setTimeout(() => {
            steps.forEach((s) => s.classList.remove("is-active"));
            currentStep = 0;
            animating = false;
            animateSteps();
          }, 2500);
        }
      }, 700);
    };

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            // Reset all first
            steps.forEach((s) => s.classList.remove("is-active"));
            currentStep = 0;
            animateSteps();
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.3 }
    );

    observer.observe(demo);
  };

  /* --- Timeline step reveal --- */
  const bindTimelineReveal = () => {
    const timeline = document.getElementById("timeline");
    if (!timeline) return;

    const steps = timeline.querySelectorAll(".timeline-step");

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            steps.forEach((step, i) => {
              setTimeout(() => {
                step.classList.add("is-revealed");
              }, i * 250);
            });
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.2 }
    );

    observer.observe(timeline);
  };

  /* --- Particle Canvas --- */
  const bindParticles = () => {
    const canvas = document.getElementById("particle-canvas");
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let particles = [];
    let animId = null;
    const PARTICLE_COUNT = 40;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };

    const createParticle = () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      radius: Math.random() * 1.5 + 0.5,
      opacity: Math.random() * 0.3 + 0.1,
      hue: Math.random() > 0.5 ? 168 : 262, // teal or violet
    });

    const init = () => {
      resize();
      particles = [];
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        particles.push(createParticle());
      }
    };

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;

        // Wrap around
        if (p.x < 0) p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = `hsla(${p.hue}, 80%, 65%, ${p.opacity})`;
        ctx.fill();
      }

      // Draw connections
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < 120) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `hsla(168, 70%, 60%, ${0.06 * (1 - dist / 120)})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      }

      animId = requestAnimationFrame(draw);
    };

    // Reduced motion check
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReducedMotion) return;

    init();
    draw();

    window.addEventListener("resize", () => {
      resize();
    });
  };

  /* --- Smooth scroll for anchor links --- */
  const bindSmoothScroll = () => {
    document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
      anchor.addEventListener("click", (e) => {
        const targetId = anchor.getAttribute("href");
        if (!targetId || targetId === "#") return;

        const target = document.querySelector(targetId);
        if (target) {
          e.preventDefault();
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });
  };

  /* --- Helper --- */
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /* --- Init --- */
  const init = () => {
    bindRevealAnimations();
    bindNavbarScroll();
    bindTypingEffect();
    bindSecurityAnimation();
    bindTimelineReveal();
    bindParticles();
    bindSmoothScroll();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
