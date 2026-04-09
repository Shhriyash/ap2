const bindRevealAnimations = () => {
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in-view");
        }
      }
    },
    { threshold: 0.2 }
  );

  for (const el of document.querySelectorAll(".reveal")) {
    observer.observe(el);
  }
};

bindRevealAnimations();
