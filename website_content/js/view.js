(()=>{function e(e){let t;return(...i)=>{t&&window.cancelAnimationFrame(t),t=window.requestAnimationFrame((()=>{e(...i)}))}}window.addEventListener("load",(function(){const t=document.querySelector(".wp-block-wporg-local-navigation-bar"),i=document.body.classList.contains("admin-bar")?32:0;if(t){const n=()=>{const{top:e}=t.getBoundingClientRect();e<=i?t.classList.add("is-sticking"):t.classList.remove("is-sticking")};document.addEventListener("scroll",e(n),{passive:!0}),n();const o=()=>{const e=t.querySelector("nav:not(.wporg-is-collapsed-nav)");if(window.innerWidth<600)return t.classList.remove("wporg-hide-page-title","wporg-show-collapsed-nav"),void e.classList.add("wporg-is-mobile-nav");e.classList.remove("wporg-is-mobile-nav");let i=t.dataset.navWidth;if(!i){const n=parseInt(window.getComputedStyle(e).gap,10)||20,o=e.querySelectorAll(".wp-block-navigation__container > li");i=[...o].reduce(((e,t)=>e+t.getBoundingClientRect().width),0)+n*(o.length-1),t.dataset.navWidth=Math.ceil(i)}const n=t.querySelector(".wp-block-site-title, div.wp-block-group");if(!n)return;let o=n.dataset.fullWidth;o||(o=[...n.children].reduce(((e,t)=>e+t.getBoundingClientRect().width),0)+10*(n.children.length-1),n.dataset.fullWidth=Math.ceil(o));const{paddingInlineStart:a="0px",paddingInlineEnd:s="0px",gap:l="0px"}=window.getComputedStyle(t),d=window.innerWidth-parseInt(a,10)-parseInt(s,10)-parseInt(l,10)-20;let c=o;n.classList.contains("wp-block-group")&&(c=n.children[0].getBoundingClientRect().width);const r=Math.ceil(o)+Math.ceil(i),p=Math.ceil(c)+Math.ceil(i);d>r?t.classList.remove("wporg-show-collapsed-nav","wporg-hide-page-title"):d>p?(t.classList.add("wporg-hide-page-title"),t.classList.remove("wporg-show-collapsed-nav")):t.classList.add("wporg-hide-page-title","wporg-show-collapsed-nav")};window.addEventListener("resize",e(o),{passive:!0}),o()}}))})();