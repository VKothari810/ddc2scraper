let opportunities = [];
let filteredOpportunities = [];

const SOURCE_LABELS = {
    sam_gov: 'SAM.gov',
    grants_gov: 'Grants.gov',
    sbir_gov: 'SBIR.gov',
    erdcwerx: 'ERDCWERX',
    dsip: 'DSIP',
    diu: 'DIU',
    darpa: 'DARPA',
    afwerx: 'AFWERX',
    navalx: 'NavalX',
    sofwerx: 'SOFWERX',
    navy_sbir: 'Navy SBIR',
    army_apps_lab: 'Army Apps Lab',
    spacewerx: 'SpaceWERX',
};

async function loadData() {
    const container = document.getElementById('opportunities-container');
    container.innerHTML = '<div class="loading">Loading opportunities...</div>';

    try {
        const response = await fetch('data.json');
        if (!response.ok) {
            throw new Error('Failed to load data');
        }
        opportunities = await response.json();
        
        populateSourceFilter();
        applyFilters();
        updateStats();
    } catch (error) {
        console.error('Error loading data:', error);
        container.innerHTML = `
            <div class="no-results">
                <p>Failed to load opportunities data.</p>
                <p style="font-size: 0.875rem; margin-top: 0.5rem;">
                    Make sure data.json exists in the dashboard folder.
                </p>
            </div>
        `;
    }
}

function populateSourceFilter() {
    const sourceFilter = document.getElementById('source-filter');
    const sources = [...new Set(opportunities.map(o => o.source))].sort();
    
    sources.forEach(source => {
        const option = document.createElement('option');
        option.value = source;
        option.textContent = SOURCE_LABELS[source] || source;
        sourceFilter.appendChild(option);
    });
}

function applyFilters() {
    const searchTerm = document.getElementById('search-input').value.toLowerCase();
    const sourceFilter = document.getElementById('source-filter').value;
    const typeFilter = document.getElementById('type-filter').value;
    const statusFilter = document.getElementById('status-filter').value;
    const relevanceFilter = parseFloat(document.getElementById('relevance-filter').value);
    const sortBy = document.getElementById('sort-select').value;

    filteredOpportunities = opportunities.filter(opp => {
        if (searchTerm) {
            const searchText = `${opp.title} ${opp.description} ${opp.agency || ''} ${opp.sub_agency || ''}`.toLowerCase();
            if (!searchText.includes(searchTerm)) return false;
        }

        if (sourceFilter && opp.source !== sourceFilter) return false;
        if (typeFilter && opp.opportunity_type !== typeFilter) return false;
        if (statusFilter && opp.status !== statusFilter) return false;
        if (opp.arctic_relevance_score < relevanceFilter) return false;

        return true;
    });

    filteredOpportunities.sort((a, b) => {
        switch (sortBy) {
            case 'relevance':
                return b.arctic_relevance_score - a.arctic_relevance_score;
            case 'close_date':
                const dateA = a.close_date ? new Date(a.close_date) : new Date('2099-12-31');
                const dateB = b.close_date ? new Date(b.close_date) : new Date('2099-12-31');
                return dateA - dateB;
            case 'posted_date':
                const postedA = a.posted_date ? new Date(a.posted_date) : new Date(0);
                const postedB = b.posted_date ? new Date(b.posted_date) : new Date(0);
                return postedB - postedA;
            case 'title':
                return a.title.localeCompare(b.title);
            default:
                return 0;
        }
    });

    renderOpportunities();
    updateStats();
}

function updateStats() {
    const now = new Date();
    const twoWeeksFromNow = new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000);

    document.getElementById('total-count').textContent = filteredOpportunities.length;
    
    document.getElementById('open-count').textContent = filteredOpportunities.filter(
        o => o.status === 'Open'
    ).length;
    
    document.getElementById('closing-soon-count').textContent = filteredOpportunities.filter(o => {
        if (!o.close_date || o.status === 'Closed') return false;
        const closeDate = new Date(o.close_date);
        return closeDate > now && closeDate <= twoWeeksFromNow;
    }).length;
    
    document.getElementById('high-relevance-count').textContent = filteredOpportunities.filter(
        o => o.arctic_relevance_score >= 0.7
    ).length;
}

function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric' 
    });
}

function getDaysUntilClose(closeDate) {
    if (!closeDate) return null;
    const now = new Date();
    const close = new Date(closeDate);
    const diff = Math.ceil((close - now) / (1000 * 60 * 60 * 24));
    return diff;
}

function getRelevanceClass(score) {
    if (score >= 0.7) return 'relevance-high';
    if (score >= 0.4) return 'relevance-medium';
    return 'relevance-low';
}

function renderOpportunities() {
    const container = document.getElementById('opportunities-container');

    if (filteredOpportunities.length === 0) {
        container.innerHTML = `
            <div class="no-results">
                <p>No opportunities match your filters.</p>
                <p style="font-size: 0.875rem; margin-top: 0.5rem;">
                    Try adjusting your search or filter criteria.
                </p>
            </div>
        `;
        return;
    }

    container.innerHTML = filteredOpportunities.map((opp, index) => {
        const daysUntilClose = getDaysUntilClose(opp.close_date);
        const isClosingSoon = daysUntilClose !== null && daysUntilClose > 0 && daysUntilClose <= 14;
        const relevancePercent = Math.round(opp.arctic_relevance_score * 100);

        return `
            <div class="opportunity-card" onclick="showDetail(${index})">
                <div class="card-header">
                    <div class="card-badges">
                        <span class="badge badge-source">${SOURCE_LABELS[opp.source] || opp.source}</span>
                        <span class="badge badge-type">${opp.opportunity_type}</span>
                        <span class="badge badge-status-${opp.status.toLowerCase()}">${opp.status}</span>
                        ${isClosingSoon ? `<span class="badge badge-deadline">${daysUntilClose}d left</span>` : ''}
                    </div>
                </div>
                <h3 class="card-title">${escapeHtml(opp.title)}</h3>
                <p class="card-agency">${escapeHtml(opp.agency || 'Unknown Agency')}${opp.sub_agency ? ' / ' + escapeHtml(opp.sub_agency) : ''}</p>
                <div class="card-dates">
                    <span>Posted: ${formatDate(opp.posted_date)}</span>
                    <span>Closes: ${formatDate(opp.close_date)}</span>
                </div>
                <div class="relevance-bar">
                    <div class="relevance-fill ${getRelevanceClass(opp.arctic_relevance_score)}" 
                         style="width: ${relevancePercent}%"></div>
                </div>
                <div class="relevance-label">Arctic Relevance: ${relevancePercent}%</div>
            </div>
        `;
    }).join('');
}

function showDetail(index) {
    const opp = filteredOpportunities[index];
    const modal = document.getElementById('detail-modal');
    const modalBody = document.getElementById('modal-body');

    const relevancePercent = Math.round(opp.arctic_relevance_score * 100);

    modalBody.innerHTML = `
        <h2>${escapeHtml(opp.title)}</h2>
        
        <div class="card-badges" style="margin-bottom: 1rem;">
            <span class="badge badge-source">${SOURCE_LABELS[opp.source] || opp.source}</span>
            <span class="badge badge-type">${opp.opportunity_type}</span>
            <span class="badge badge-status-${opp.status.toLowerCase()}">${opp.status}</span>
        </div>

        <div class="modal-meta">
            <div class="meta-item">
                <strong>Agency</strong>
                ${escapeHtml(opp.agency || 'N/A')}
            </div>
            <div class="meta-item">
                <strong>Sub-Agency</strong>
                ${escapeHtml(opp.sub_agency || 'N/A')}
            </div>
            <div class="meta-item">
                <strong>Office</strong>
                ${escapeHtml(opp.office || 'N/A')}
            </div>
            <div class="meta-item">
                <strong>Solicitation #</strong>
                ${escapeHtml(opp.solicitation_number || 'N/A')}
            </div>
            <div class="meta-item">
                <strong>Posted Date</strong>
                ${formatDate(opp.posted_date)}
            </div>
            <div class="meta-item">
                <strong>Close Date</strong>
                ${formatDate(opp.close_date)}
            </div>
            <div class="meta-item">
                <strong>Arctic Relevance</strong>
                ${relevancePercent}%
            </div>
            <div class="meta-item">
                <strong>Set-Aside</strong>
                ${escapeHtml(opp.set_aside || 'None')}
            </div>
        </div>

        ${opp.description ? `
        <div class="modal-section">
            <h3>Description</h3>
            <p>${escapeHtml(opp.description)}</p>
        </div>
        ` : ''}

        ${opp.arctic_relevance_reasoning ? `
        <div class="modal-section">
            <h3>Arctic Relevance Analysis</h3>
            <p>${escapeHtml(opp.arctic_relevance_reasoning)}</p>
        </div>
        ` : ''}

        ${opp.arctic_keywords_found && opp.arctic_keywords_found.length > 0 ? `
        <div class="modal-section">
            <h3>Arctic Keywords Found</h3>
            <ul class="keywords-list">
                ${opp.arctic_keywords_found.map(kw => `<li>${escapeHtml(kw)}</li>`).join('')}
            </ul>
        </div>
        ` : ''}

        ${opp.naics_codes && opp.naics_codes.length > 0 ? `
        <div class="modal-section">
            <h3>NAICS Codes</h3>
            <p>${opp.naics_codes.join(', ')}</p>
        </div>
        ` : ''}

        <a href="${escapeHtml(opp.source_url)}" target="_blank" class="source-link">
            View Original Source
        </a>
    `;

    modal.classList.add('active');
}

function closeModal() {
    document.getElementById('detail-modal').classList.remove('active');
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

document.getElementById('search-input').addEventListener('input', debounce(applyFilters, 300));
document.getElementById('source-filter').addEventListener('change', applyFilters);
document.getElementById('type-filter').addEventListener('change', applyFilters);
document.getElementById('status-filter').addEventListener('change', applyFilters);
document.getElementById('relevance-filter').addEventListener('input', function() {
    document.getElementById('relevance-value').textContent = this.value;
    applyFilters();
});
document.getElementById('sort-select').addEventListener('change', applyFilters);

document.getElementById('modal-close').addEventListener('click', closeModal);
document.getElementById('detail-modal').addEventListener('click', function(e) {
    if (e.target === this) closeModal();
});
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeModal();
});

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

loadData();
