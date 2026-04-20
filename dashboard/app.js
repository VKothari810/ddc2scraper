// Dominion - Arctic Defense Opportunities Database

let allOpportunities = [];
let filteredOpportunities = [];
let displayedCount = 0;
const ITEMS_PER_PAGE = 24;
let currentView = 'grid';

// DOM Elements
const searchInput = document.getElementById('search-input');
const filterSource = document.getElementById('filter-source');
const filterType = document.getElementById('filter-type');
const filterStatus = document.getElementById('filter-status');
const filterRelevance = document.getElementById('filter-relevance');
const sortBy = document.getElementById('sort-by');
const resultsCount = document.getElementById('results-count');
const opportunitiesGrid = document.getElementById('opportunities-grid');
const loadMoreBtn = document.getElementById('load-more');
const modalOverlay = document.getElementById('modal-overlay');
const modalContent = document.getElementById('modal-content');
const modalClose = document.getElementById('modal-close');

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await loadData();
    setupEventListeners();
    setupViewToggle();
});

async function loadData() {
    try {
        const response = await fetch('data.json');
        if (!response.ok) throw new Error('Failed to load data');
        allOpportunities = await response.json();
        
        populateFilters();
        applyFilters();
    } catch (error) {
        console.error('Error loading data:', error);
        opportunitiesGrid.innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 4rem; color: var(--text-muted);">
                Failed to load opportunities. Please refresh the page.
            </div>
        `;
    }
}

function populateFilters() {
    const sources = [...new Set(allOpportunities.map(o => o.source))].sort();
    const types = [...new Set(allOpportunities.map(o => o.opportunity_type))].sort();
    
    sources.forEach(source => {
        const option = document.createElement('option');
        option.value = source;
        option.textContent = formatSourceName(source);
        filterSource.appendChild(option);
    });
    
    types.forEach(type => {
        const option = document.createElement('option');
        option.value = type;
        option.textContent = type;
        filterType.appendChild(option);
    });
}

function formatSourceName(source) {
    const names = {
        'sam_gov': 'SAM.gov',
        'grants_gov': 'Grants.gov',
        'sbir_gov': 'SBIR.gov',
        'erdcwerx': 'ERDCWERX',
        'dsip': 'DSIP',
        'diu': 'DIU',
        'darpa': 'DARPA',
        'afwerx': 'AFWERX',
        'navalx': 'NavalX',
        'sofwerx': 'SOFWERX',
        'navy_sbir': 'Navy SBIR',
        'army_apps_lab': 'Army Apps Lab',
        'spacewerx': 'SpaceWERX'
    };
    return names[source] || source.toUpperCase();
}

function setupEventListeners() {
    searchInput.addEventListener('input', debounce(applyFilters, 300));
    filterSource.addEventListener('change', applyFilters);
    filterType.addEventListener('change', applyFilters);
    filterStatus.addEventListener('change', applyFilters);
    filterRelevance.addEventListener('change', applyFilters);
    sortBy.addEventListener('change', applyFilters);
    loadMoreBtn.addEventListener('click', loadMore);
    modalClose.addEventListener('click', closeModal);
    modalOverlay.addEventListener('click', (e) => {
        if (e.target === modalOverlay) closeModal();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });
}

function setupViewToggle() {
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentView = btn.dataset.view;
            opportunitiesGrid.className = currentView === 'list' ? 'opportunities-grid list-view' : 'opportunities-grid';
        });
    });
}

function applyFilters() {
    const searchTerm = searchInput.value.toLowerCase();
    const source = filterSource.value;
    const type = filterType.value;
    const status = filterStatus.value;
    const relevance = parseFloat(filterRelevance.value) || 0;
    const sort = sortBy.value;
    
    filteredOpportunities = allOpportunities.filter(opp => {
        if (searchTerm && !matchesSearch(opp, searchTerm)) return false;
        if (source && opp.source !== source) return false;
        if (type && opp.opportunity_type !== type) return false;
        if (status && opp.status !== status) return false;
        if (relevance && (opp.arctic_relevance_score || 0) < relevance) return false;
        return true;
    });
    
    sortOpportunities(sort);
    displayedCount = 0;
    opportunitiesGrid.innerHTML = '';
    loadMore();
    updateResultsCount();
}

function matchesSearch(opp, term) {
    const searchFields = [
        opp.title,
        opp.description,
        opp.agency,
        opp.sub_agency,
        opp.office,
        opp.solicitation_number,
        ...(opp.arctic_keywords_found || [])
    ].filter(Boolean).join(' ').toLowerCase();
    
    return searchFields.includes(term);
}

function sortOpportunities(sort) {
    filteredOpportunities.sort((a, b) => {
        switch (sort) {
            case 'relevance':
                return (b.arctic_relevance_score || 0) - (a.arctic_relevance_score || 0);
            case 'date-desc':
                return new Date(b.posted_date || 0) - new Date(a.posted_date || 0);
            case 'date-asc':
                return new Date(a.posted_date || 0) - new Date(b.posted_date || 0);
            case 'closing':
                const aClose = a.close_date ? new Date(a.close_date) : new Date('2099-12-31');
                const bClose = b.close_date ? new Date(b.close_date) : new Date('2099-12-31');
                return aClose - bClose;
            case 'title':
                return a.title.localeCompare(b.title);
            default:
                return 0;
        }
    });
}

function loadMore() {
    const toLoad = filteredOpportunities.slice(displayedCount, displayedCount + ITEMS_PER_PAGE);
    toLoad.forEach(opp => {
        opportunitiesGrid.appendChild(createCard(opp));
    });
    displayedCount += toLoad.length;
    loadMoreBtn.style.display = displayedCount < filteredOpportunities.length ? 'block' : 'none';
}

function updateResultsCount() {
    const total = filteredOpportunities.length;
    const arctic = filteredOpportunities.filter(o => o.arctic_relevance_score >= 0.3).length;
    resultsCount.textContent = `${total.toLocaleString()} opportunities • ${arctic} arctic relevant`;
}

function createCard(opp) {
    const card = document.createElement('div');
    card.className = 'opp-card';
    card.onclick = () => openModal(opp);
    
    const relevance = opp.arctic_relevance_score || 0;
    const relevanceClass = relevance >= 0.7 ? 'relevance-high' : relevance >= 0.3 ? 'relevance-medium' : 'relevance-low';
    const relevancePercent = Math.round(relevance * 100);
    
    const typeClass = getTypeClass(opp.opportunity_type);
    const statusClass = getStatusClass(opp.status);
    
    const agency = opp.agency || 'Unknown Agency';
    const postedDate = opp.posted_date ? formatDate(opp.posted_date) : '—';
    const closeDate = opp.close_date ? formatDate(opp.close_date) : '—';
    
    card.innerHTML = `
        <div class="opp-card-header">
            <span class="opp-source">${formatSourceName(opp.source)}</span>
            <span class="opp-relevance ${relevanceClass}">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M12 6v6l4 2"/>
                </svg>
                ${relevancePercent}%
            </span>
        </div>
        <h3 class="opp-title">${escapeHtml(opp.title)}</h3>
        <div class="opp-meta">
            <span class="opp-badge ${typeClass}">${opp.opportunity_type}</span>
            <span class="opp-badge ${statusClass}">${opp.status}</span>
        </div>
        <p class="opp-agency">${escapeHtml(agency)}</p>
        <div class="opp-dates">
            <div class="opp-date-item">
                <span class="opp-date-label">Posted</span>
                <span class="opp-date-value">${postedDate}</span>
            </div>
            <div class="opp-date-item">
                <span class="opp-date-label">Closes</span>
                <span class="opp-date-value">${closeDate}</span>
            </div>
        </div>
    `;
    
    return card;
}

function getTypeClass(type) {
    const typeMap = {
        'SBIR': 'type-sbir',
        'STTR': 'type-sttr',
        'BAA': 'type-baa',
        'Grant': 'type-grant',
        'CSO': 'type-cso'
    };
    return typeMap[type] || '';
}

function getStatusClass(status) {
    const statusMap = {
        'Open': 'status-open',
        'Forecasted': 'status-forecasted',
        'Closed': 'status-closed'
    };
    return statusMap[status] || '';
}

function openModal(opp) {
    const relevance = opp.arctic_relevance_score || 0;
    const relevancePercent = Math.round(relevance * 100);
    const relevanceClass = relevance >= 0.7 ? 'relevance-high' : relevance >= 0.3 ? 'relevance-medium' : 'relevance-low';
    
    const typeClass = getTypeClass(opp.opportunity_type);
    const statusClass = getStatusClass(opp.status);
    
    const keywords = opp.arctic_keywords_found || [];
    const keywordsHtml = keywords.length > 0 
        ? keywords.map(k => `<span class="modal-keyword">${escapeHtml(k)}</span>`).join('')
        : '<span style="color: var(--text-muted)">None detected</span>';
    
    modalContent.innerHTML = `
        <div class="modal-header">
            <div class="modal-badges">
                <span class="opp-source">${formatSourceName(opp.source)}</span>
                <span class="opp-badge ${typeClass}">${opp.opportunity_type}</span>
                <span class="opp-badge ${statusClass}">${opp.status}</span>
            </div>
            <h2 class="modal-title">${escapeHtml(opp.title)}</h2>
            <p class="modal-agency">${escapeHtml(opp.agency || 'Unknown Agency')}</p>
        </div>
        
        <div class="modal-grid">
            <div class="modal-field">
                <span class="modal-field-label">Solicitation #</span>
                <span class="modal-field-value">${escapeHtml(opp.solicitation_number || '—')}</span>
            </div>
            <div class="modal-field">
                <span class="modal-field-label">Sub-Agency</span>
                <span class="modal-field-value">${escapeHtml(opp.sub_agency || '—')}</span>
            </div>
            <div class="modal-field">
                <span class="modal-field-label">Office</span>
                <span class="modal-field-value">${escapeHtml(opp.office || '—')}</span>
            </div>
            <div class="modal-field">
                <span class="modal-field-label">Arctic Relevance</span>
                <span class="modal-field-value ${relevanceClass}">${relevancePercent}%</span>
            </div>
            <div class="modal-field">
                <span class="modal-field-label">Posted Date</span>
                <span class="modal-field-value">${opp.posted_date ? formatDate(opp.posted_date) : '—'}</span>
            </div>
            <div class="modal-field">
                <span class="modal-field-label">Close Date</span>
                <span class="modal-field-value">${opp.close_date ? formatDate(opp.close_date) : '—'}</span>
            </div>
        </div>
        
        ${opp.description ? `
        <div class="modal-section">
            <h4 class="modal-section-title">Description</h4>
            <p class="modal-section-content">${escapeHtml(opp.description)}</p>
        </div>
        ` : ''}
        
        <div class="modal-section">
            <h4 class="modal-section-title">Arctic Relevance Analysis</h4>
            <p class="modal-section-content">${escapeHtml(opp.arctic_relevance_reasoning || 'No analysis available')}</p>
        </div>
        
        <div class="modal-section">
            <h4 class="modal-section-title">Keywords Found</h4>
            <div class="modal-keywords">${keywordsHtml}</div>
        </div>
        
        <div class="modal-action">
            <a href="${opp.source_url}" target="_blank" rel="noopener" class="modal-btn">
                View Original Source
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                    <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
            </a>
        </div>
    `;
    
    modalOverlay.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    modalOverlay.classList.remove('active');
    document.body.style.overflow = '';
}

function formatDate(dateStr) {
    if (!dateStr) return '—';
    const date = new Date(dateStr);
    if (isNaN(date)) return dateStr;
    return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric' 
    });
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

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
