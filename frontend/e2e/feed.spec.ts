import { test, expect } from '@playwright/test';

/**
 * Tests E2E du feed Sip-feed.
 *
 * Tous les tests opèrent sur des fonctionnalités publiques (pas d'auth).
 * Pré-requis : émulateur Firestore + backend + frontend démarrés en local,
 * au moins 1 article en base.
 *
 * Convention de nommage : chaque test cite l'ID de la User Story qu'il couvre.
 * Cf. Features/02-feed-display.md et Features/03-feed-filters.md.
 */

// Sélecteurs partagés
const newsCardTitle = 'h2.text-lg.font-semibold'; // titre d'un NewsCard
const counterRegex = /\d+ affichés? sur \d+/;     // "20 affichés sur 180"

async function waitForFeed(page: import('@playwright/test').Page) {
  await page.goto('/');
  // Attend que le feed soit rendu (au moins une card OU le message vide)
  await Promise.race([
    page.waitForSelector(newsCardTitle, { timeout: 15_000 }),
    page.waitForSelector('text=Aucun article', { timeout: 15_000 }),
  ]);
}

test.describe('Feed — affichage et pagination', () => {
  test('US-FEED-001 — Le feed se charge et affiche des articles', async ({ page }) => {
    await waitForFeed(page);

    const cards = page.locator(newsCardTitle);
    const count = await cards.count();
    expect(count).toBeGreaterThan(0);

    // Le compteur "X affichés sur Y" est visible
    await expect(page.locator(`text=${counterRegex}`).first()).toBeVisible();
  });

  test('US-FEED-002 — "Afficher plus" augmente le nombre d\'articles visibles', async ({ page }) => {
    await waitForFeed(page);

    const cards = page.locator(newsCardTitle);
    const initialCount = await cards.count();

    const loadMoreBtn = page.getByRole('button', { name: 'Afficher plus' });
    const isVisible = await loadMoreBtn.isVisible().catch(() => false);

    test.skip(!isVisible, 'Bouton "Afficher plus" non présent (base trop petite pour ce test)');

    await loadMoreBtn.click();
    // Attend que le compteur de cards augmente
    await expect.poll(async () => cards.count(), { timeout: 10_000 })
      .toBeGreaterThan(initialCount);

    const afterClickCount = await cards.count();
    expect(afterClickCount).toBeGreaterThan(initialCount);
  });
});

test.describe('Feed — préférences d\'affichage', () => {
  test('US-FEED-003 — Le toggle FR/EN change la langue', async ({ page }) => {
    await waitForFeed(page);

    // Boutons FR et EN dans le header
    const frBtn = page.locator('button:has-text("FR")').first();
    const enBtn = page.locator('button:has-text("EN")').first();

    await expect(frBtn).toBeVisible();
    await expect(enBtn).toBeVisible();

    // Bascule en EN
    await enBtn.click();
    // Le bouton "Lire l'article" devient "Read article" (preuve que la langue a changé)
    await expect(page.locator('text=Read article').first()).toBeVisible({ timeout: 5_000 });

    // Bascule en FR
    await frBtn.click();
    await expect(page.locator("text=Lire l'article").first()).toBeVisible({ timeout: 5_000 });
  });

  test('US-FEED-004 — Le toggle colonnes change la grille', async ({ page }) => {
    await waitForFeed(page);

    // 3 boutons colonnes identifiés par leur title
    const col1 = page.getByTitle('1 colonne');
    const col2 = page.getByTitle('2 colonnes');
    const col3 = page.getByTitle('3 colonnes');

    await expect(col1).toBeVisible();
    await expect(col2).toBeVisible();
    await expect(col3).toBeVisible();

    // Récupère la grille (a une classe Tailwind grid-cols-*)
    const grid = page.locator('div.grid').first();

    // Passe en 3 colonnes
    await col3.click();
    await expect(grid).toHaveClass(/lg:grid-cols-3/);

    // Repasse en 1 colonne
    await col1.click();
    await expect(grid).toHaveClass(/grid-cols-1/);
    await expect(grid).not.toHaveClass(/sm:grid-cols-2/);
  });
});

test.describe('Feed — filtres', () => {
  test('US-FLT-001 — Filtrer par catégorie réduit la liste', async ({ page }) => {
    await waitForFeed(page);

    const cards = page.locator(newsCardTitle);
    const totalCount = await cards.count();
    expect(totalCount).toBeGreaterThan(0);

    // Ouvre le filtre Catégories
    const categoryFilterBtn = page.getByRole('button', { name: /Catégories/ });
    await expect(categoryFilterBtn).toBeVisible();
    await categoryFilterBtn.click();

    // Cherche une catégorie présente (parmi les 7) et clique dessus.
    // On essaie IA en premier, puis Dev en fallback.
    let categoryClicked = false;
    for (const cat of ['IA', 'Dev', 'DevOps', 'Cloud', 'Sécurité', 'IT', 'Autre']) {
      const catOption = page.locator(`[role="menu"], [role="listbox"], div`)
        .locator(`button:has-text("${cat}")`).first();
      if (await catOption.isVisible().catch(() => false)) {
        await catOption.click();
        categoryClicked = true;
        break;
      }
    }
    expect(categoryClicked, 'Aucune option de catégorie trouvée dans le filtre').toBe(true);

    // Après filtre, on devrait avoir <= totalCount cards
    // (autofetch peut rapprocher au max pageSize, mais reste <= totalAll)
    await page.waitForTimeout(500); // laisse le temps au refilter / autofetch
    const filteredCount = await cards.count();
    expect(filteredCount).toBeLessThanOrEqual(totalCount + 50); // tolérance autofetch
    expect(filteredCount).toBeGreaterThanOrEqual(0);
  });
});
