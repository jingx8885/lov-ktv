(() => {
  const links = [...document.querySelectorAll(".lp-toc a")];
  const sections = links
    .map((link) => document.querySelector(link.getAttribute("href") || ""))
    .filter(Boolean);
  if (!links.length || !("IntersectionObserver" in window)) return;

  const seen = new Map();
  const draw = () => {
    const active = sections.find((section) => seen.get(section));
    links.forEach((link) => {
      const on = active && link.getAttribute("href") === `#${active.id}`;
      link.classList.toggle("is-on", Boolean(on));
    });
  };
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => seen.set(entry.target, entry.isIntersecting && entry.intersectionRatio > 0.28));
      draw();
    },
    { rootMargin: "-20% 0px -45% 0px", threshold: [0.28, 0.6] },
  );
  sections.forEach((section) => io.observe(section));
})();
