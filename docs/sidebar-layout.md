# Sidebar layout verification — 13 October 2026

History links were flex children that could shrink below their text height when
the sidebar ran out of vertical space. Long history became cramped while the
non-scrolling outer container clipped controls.

The sidebar now uses the dynamic viewport height, stable history rows and
independent history scrolling. Its body can scroll at shorter heights while the
brand and account/footer controls stay accessible. Very short screens have an
outer scroll fallback. Long conversation/account names ellipsize with full labels
available on hover or to assistive technology. The font and dark palette remain.

The mobile drawer ignores desktop collapse state, hides closed navigation from
keyboard interaction, confines focus while open, restores focus on Escape and
closes on navigation. Page scrolling is unlocked when the drawer closes.
Collapsed history is absent from keyboard navigation. Reduced motion is respected.

Eighteen isolated browser cases passed with synthetic account/history data:
stable rows and visible footer at 1280×900, 1280×640, 1024×560, 1024×480 and
1024×400; independent history scrolling/See all; pinned ordering; long international
titles/account names; history collapse/dialog; compact navigation; mobile after
desktop collapse; keyboard focus/Escape; 320×568, 390×844 and 768×640; a 320px-high
scroll fallback; reduced motion. No client exceptions occurred.

The complete frontend suite passed 115 tests. TypeScript passed and scoped lint
had zero errors, with existing effect-maintenance warnings. Hosted verification
is performed against the published AWS bundle after deployment.
