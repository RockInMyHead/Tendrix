let currentPage = 1;
let currentParams = {};
let totalRecords = 0;

document.getElementById('searchForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    currentPage = 1;
    await performSearch(false); // Changed to false for new search
});

// --- AUTH LOGIC ---
const token = localStorage.getItem('access_token');

async function checkAuth() {
    const loginLink = document.getElementById('loginLink');
    const adminLink = document.getElementById('adminLink');
    const logoutLink = document.getElementById('logoutLink');
    const userInfo = document.getElementById('userInfo');

    if (!token) {
        if (loginLink) loginLink.style.display = 'block';
        if (logoutLink) logoutLink.style.display = 'none';
        if (adminLink) adminLink.style.display = 'none';
        if (userInfo) userInfo.textContent = '';
        return;
    }

    try {
        const response = await fetch('/users/me', {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            const user = await response.json();
            if (userInfo) userInfo.textContent = user.username;
            if (loginLink) loginLink.style.display = 'none';
            if (logoutLink) logoutLink.style.display = 'block';
            if (user.is_admin && adminLink) {
                adminLink.style.display = 'block';
            } else if (adminLink) {
                adminLink.style.display = 'none';
            }
        } else {
            localStorage.removeItem('access_token');
            if (loginLink) loginLink.style.display = 'block';
            if (logoutLink) logoutLink.style.display = 'none';
            if (adminLink) adminLink.style.display = 'none';
            if (userInfo) userInfo.textContent = '';
        }
    } catch (e) {
        console.error("Auth check failed", e);
        localStorage.removeItem('access_token');
        if (loginLink) loginLink.style.display = 'block';
        if (logoutLink) logoutLink.style.display = 'none';
        if (adminLink) adminLink.style.display = 'none';
        if (userInfo) userInfo.textContent = '';
    }
}

function logout() {
    localStorage.removeItem('access_token');
    window.location.reload();
}

// Initial check
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    const logoutBtn = document.getElementById('logoutLink');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            logout();
        });
    }
});

async function performSearch(isLoadMore = false) {
    if (!token) {
        alert("Пожалуйста, войдите в систему, чтобы пользоваться поиском.");
        window.location.href = '/login.html';
        return;
    }

    const resultsContainer = document.getElementById('results');
    const loader = document.getElementById('loader');
    const noResults = document.getElementById('noResults');
    const searchBtn = document.getElementById('searchBtn');
    const loadMoreContainer = document.getElementById('loadMoreContainer');
    const loadMoreBtn = document.getElementById('loadMoreBtn');
    const totalCountEl = document.getElementById('totalCount');

    // Get filter values from form inputs
    const searchString = document.getElementById('searchString').value;
    const priceFrom = document.getElementById('priceFrom').value;
    const priceTo = document.getElementById('priceTo').value;
    const fz44 = document.getElementById('fz44').checked;
    const fz223 = document.getElementById('fz223').checked;
    const publishDateFrom = document.getElementById('publishDateFrom').value;
    const companyDescription = document.getElementById('companyDescription').value;

    if (!isLoadMore) {
        currentPage = 1;
        resultsContainer.innerHTML = '';
        noResults.classList.add('hidden');
        if (loadMoreContainer) loadMoreContainer.classList.add('hidden');
        if (totalCountEl) totalCountEl.innerText = '';
        searchBtn.disabled = true;
        searchBtn.innerText = 'Загрузка...';
        loader.classList.remove('hidden');
    } else {
        loadMoreBtn.disabled = true;
        loadMoreBtn.innerText = 'Загрузка...';
    }

    try {
        // Build params
        const params = new URLSearchParams({
            search_string: searchString,
            law_44: fz44,
            law_223: fz223,
            page: currentPage,
            records_per_page: 50 // Matching backend default
        });

        if (priceFrom) params.append('price_from', priceFrom);
        if (priceTo) params.append('price_to', priceTo);
        if (publishDateFrom) params.append('publish_date_from', publishDateFrom);
        if (companyDescription) params.append('company_description', companyDescription);

        const response = await fetch(`/api/search?${params.toString()}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const result = await response.json();

        loader.classList.add('hidden');
        searchBtn.disabled = false;
        searchBtn.innerText = 'Найти контракты';

        if (result.status === 'success') {
            totalRecords = result.total || 0;
            if (totalCountEl) {
                totalCountEl.innerText = `Всего найдено: ${new Intl.NumberFormat('ru-RU').format(totalRecords)}`;
            }

            if (result.data && result.data.length > 0) {
                renderResults(result.data);

                // Show/Hide Load More
                if (!loadMoreContainer) return; // safety

                const loadedCount = document.querySelectorAll('.contract-card').length;
                if (loadedCount < totalRecords) {
                    loadMoreContainer.classList.remove('hidden');
                    loadMoreBtn.disabled = false;
                    loadMoreBtn.innerText = 'Загрузить еще';
                } else {
                    loadMoreContainer.classList.add('hidden');
                }
            } else if (isNewSearch) {
                noResults.classList.remove('hidden');
            }
        } else {
            if (isNewSearch) noResults.classList.remove('hidden');
        }

    } catch (error) {
        console.error('Search error:', error);
        loader.classList.add('hidden');
        searchBtn.disabled = false;
        searchBtn.innerText = 'Найти контракты';

        if (isNewSearch) {
            noResults.classList.remove('hidden');
            noResults.innerHTML = `<p style="color: #ef4444;">Ошибка: ${error.message}</p>`;
        }
    }
}

// Add Load More button logic manually since it's dynamic
// Check if button exists, if not create logic (we will add button to HTML next)
document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('loadMoreBtn');
    if (btn) {
        btn.addEventListener('click', async () => {
            currentPage++;
            await performSearch(false);
        });
    }
});

function renderResults(contracts) {
    const container = document.getElementById('results');

    contracts.forEach((contract, index) => {
        const card = document.createElement('div');
        card.className = 'contract-card';
        // Add staggered animation effect
        card.style.animationDelay = `${(index % 20) * 0.05}s`;

        const formattedPrice = contract.price
            ? new Intl.NumberFormat('ru-RU').format(contract.price) + ' ' + (contract.currency || '₽')
            : 'Цена не указана';

        // Relevance Badge & Reason Logic
        let relevanceHtml = '';
        if (contract.relevance && contract.relevance > 0) {
            relevanceHtml = `
                <div class="relevance-badge" title="Соответствие описанию компании">
                    <span>★ ${contract.relevance}%</span>
                </div>
            `;
        }

        let reasonHtml = '';
        if (contract.reason) {
            reasonHtml = `<div class="relevance-reason">${contract.reason}</div>`;
        }

        card.innerHTML = `
            ${relevanceHtml}
            <div class="card-header">
                <span class="contract-number">№ ${contract.number}</span>
                ${contract.stage ? `<span class="stage-badge">${contract.stage}</span>` : ''}
            </div>
            ${reasonHtml}
            <div class="price">${formattedPrice}</div>
            <div class="subject" title="${contract.subject}">${contract.subject}</div>
            <div class="card-footer">
                <div class="info-row">
                    <span class="label">Заказчик:</span>
                    <span class="value" title="${contract.customer || '-'}">${contract.customer || '-'}</span>
                </div>
                <div class="info-row">
                    <span class="label">Поставщик:</span>
                    <span class="value" title="${contract.supplier || '-'}">${contract.supplier || '-'}</span>
                </div>
                <div class="info-row" style="margin-top: 0.5rem;">
                    <a href="${contract.link}" target="_blank" style="color: var(--accent); text-decoration: none; font-weight: 600; font-size: 0.8rem;">
                        Открыть карточку →
                    </a>
                    <span class="label" style="font-size: 0.75rem;">${contract.update_date || ''}</span>
                </div>
            </div>
        `;

        container.appendChild(card);
    });
}
