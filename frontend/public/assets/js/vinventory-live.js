(function () {
    const AUTH_KEY = 'vch_auth_session';
    const SEARCH_CONTEXT_KEY = 'vch_inventory_search_context';
    const DEFAULT_IMAGE = '/assets/images/about/05.webp';
    const AUCTION_DEFAULT_IMAGE = '/assets/images/portfolio/VCH%20Auction%20default%20image.webp';
    const CONDITION_REPORT_ELIGIBLE_FUNDING_STATES = {
        PRE_APPROVED: true,
        TERMS_ACCEPTED: true,
        FINAL_APPROVAL_PENDING: true,
        FULLY_FUNDED: true,
        CASH_BUYER: true
    };

    const state = {
        auth: null,
        deal: null,
        rows: [],
        pagination: {
            page: 1,
            per_page: 18,
            total: 0,
            total_pages: 0,
            has_next: false,
            has_prev: false
        },
        sync: null,
        garage: [],
        modalVehicle: null,
        modalImage: null,
        detailCache: {},
        facets: {},
        taxonomy: {},
        pendingAction: null
    };

    const el = {
        authEmail: document.getElementById('authEmail'),
        authPassword: document.getElementById('authPassword'),
        authLoginBtn: document.getElementById('authLoginBtn'),
        authLogoutBtn: document.getElementById('authLogoutBtn'),
        authStatus: document.getElementById('authStatus'),
        dealStage: document.getElementById('vinvDealStage'),

        form: document.getElementById('vinvFilterForm'),
        resetBtn: document.getElementById('vinvResetFilters'),
        grid: document.getElementById('vinvGrid'),
        paginationTop: document.getElementById('vinvPaginationTop'),
        pagination: document.getElementById('vinvPagination'),
        error: document.getElementById('vinvError'),
        resultCount: document.getElementById('vinvResultCount'),
        syncBadge: document.getElementById('vinvSyncBadge'),
        activeFilters: document.getElementById('vinvActiveFilters'),

        garageCount: document.getElementById('vinvGarageCount'),
        garageList: document.getElementById('vinvGarageList'),

        modal: document.getElementById('vinventoryModal'),
        modalClose: document.getElementById('vinvModalClose'),
        modalBody: document.getElementById('vinvModalBody'),

        authPromptModal: document.getElementById('vinvAuthRequiredModal'),
        authPromptClose: document.getElementById('vinvAuthRequiredClose'),
        authPromptMessage: document.getElementById('vinvAuthPromptMessage'),
        authPromptEmail: document.getElementById('vinvAuthPromptEmail'),
        authPromptPassword: document.getElementById('vinvAuthPromptPassword'),
        authPromptLogin: document.getElementById('vinvAuthPromptLogin'),
        authPromptRegister: document.getElementById('vinvAuthPromptRegister'),
        authPromptStatus: document.getElementById('vinvAuthPromptStatus')
    };

    function setStatus(message, isError) {
        if (!el.authStatus) return;
        el.authStatus.textContent = message || '';
        el.authStatus.style.color = isError ? '#fecaca' : '#bfdbfe';
    }

    function setError(message) {
        if (!el.error) return;
        if (!message) {
            el.error.innerHTML = '';
            return;
        }
        el.error.innerHTML = '<div class="vinv-alert">' + escapeHtml(message) + '</div>';
    }

    function setAuthPromptStatus(message, isError) {
        if (!el.authPromptStatus) return;
        el.authPromptStatus.textContent = message || '';
        el.authPromptStatus.style.color = isError ? '#fecaca' : '#bfdbfe';
    }

    function setDealBadge() {
        if (!el.dealStage) return;
        if (state.deal && state.deal.stage) {
            el.dealStage.textContent = 'Deal Stage: ' + state.deal.stage;
        } else {
            el.dealStage.textContent = 'Deal Stage: Guest';
        }
    }

    function isAuctionSource(sourceType) {
        return sourceType === 'ove' || sourceType === 'auction';
    }

    function isAuctionItem(item) {
        return !!(item && (item.source_category === 'auction' || isAuctionSource(item.source_type)));
    }

    function fallbackImageFor(item) {
        if (item && item.thumbnail) return item.thumbnail;
        if (item && isAuctionItem(item)) return AUCTION_DEFAULT_IMAGE;
        return DEFAULT_IMAGE;
    }

    function saveSearchContext() {
        if (!el.form) return;
        var filters = currentFilters();
        try {
            localStorage.setItem(SEARCH_CONTEXT_KEY, JSON.stringify({
                zip_code: filters.zip_code,
                radius: filters.radius || '50'
            }));
        } catch (error) {
            return;
        }
    }

    function restoreSearchContext() {
        if (!el.form) return;
        try {
            var raw = localStorage.getItem(SEARCH_CONTEXT_KEY);
            if (!raw) return;
            var parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== 'object') return;
            var zipInput = el.form.querySelector('[name="zip_code"]');
            var radiusSelect = el.form.querySelector('[name="radius"]');
            if (zipInput && parsed.zip_code) zipInput.value = String(parsed.zip_code).trim();
            if (radiusSelect && parsed.radius) radiusSelect.value = String(parsed.radius).trim();
        } catch (error) {
            return;
        }
    }

    function dealAllowsConditionReport() {
        if (state.deal && typeof state.deal.condition_report_eligible === 'boolean') {
            return state.deal.condition_report_eligible;
        }
        var fundingState = state.deal && state.deal.funding_state;
        return !!(fundingState && CONDITION_REPORT_ELIGIBLE_FUNDING_STATES[fundingState]);
    }

    function conditionReportEligibilityMessage() {
        if (state.deal && state.deal.condition_report_eligibility_reason) {
            return state.deal.condition_report_eligibility_reason;
        }
        return 'Condition/inspection report requests require being a pre-approved buyer.';
    }

    function hasConditionReport(vehicle) {
        return !!(
            vehicle
            && vehicle.condition_report
            && typeof vehicle.condition_report === 'object'
            && Object.keys(vehicle.condition_report).length
        );
    }

    function loadAuth() {
        try {
            var raw = localStorage.getItem(AUTH_KEY);
            if (!raw) return null;
            var parsed = JSON.parse(raw);
            if (!parsed || !parsed.access_token) return null;
            return parsed;
        } catch (error) {
            return null;
        }
    }

    function titleCase(value) {
        return String(value || '')
            .replace(/[_-]+/g, ' ')
            .split(/\s+/)
            .filter(Boolean)
            .map(function (part) {
                return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
            })
            .join(' ');
    }

    function formatFilterValue(label, value) {
        if (label === 'State') return String(value || '').toUpperCase();
        if (label === 'Source' && ['ove', 'auction'].indexOf(String(value || '').toLowerCase()) !== -1) return 'Auction';
        return titleCase(value);
    }

    function saveAuth(auth) {
        state.auth = auth;
        localStorage.setItem(AUTH_KEY, JSON.stringify(auth));
        if (el.authEmail && auth.email) el.authEmail.value = auth.email;
        if (el.authLogoutBtn) el.authLogoutBtn.style.display = 'inline-flex';
        setStatus('Signed in as ' + (auth.email || 'buyer'), false);
    }

    function clearAuth() {
        state.auth = null;
        state.deal = null;
        state.garage = [];
        localStorage.removeItem(AUTH_KEY);
        if (el.authLogoutBtn) el.authLogoutBtn.style.display = 'none';
        setStatus('Signed out', false);
        renderGarage();
        setDealBadge();
    }

    async function api(path, options) {
        var opts = options || {};
        var headers = {
            'Content-Type': 'application/json'
        };

        if (opts.token) {
            headers.Authorization = 'Bearer ' + opts.token;
        }

        var response = await fetch(path, {
            method: opts.method || 'GET',
            headers: headers,
            body: opts.body ? JSON.stringify(opts.body) : undefined
        });

        var payload;
        try {
            payload = await response.json();
        } catch (error) {
            payload = {
                status: 'error',
                data: null,
                error: { message: 'Invalid server response' }
            };
        }

        if (!payload || typeof payload !== 'object') {
            payload = {
                status: 'error',
                data: null,
                error: { message: 'Invalid server response' }
            };
        }

        if (response.status >= 400 && payload.status !== 'error') {
            payload = {
                status: 'error',
                data: null,
                error: {
                    message: payload.detail || (payload.error && payload.error.message) || response.statusText || 'Request failed'
                }
            };
        }

        if (response.status >= 400 && payload.status === 'error' && (!payload.error || !payload.error.message)) {
            payload.error = {
                message: payload.detail || response.statusText || 'Request failed'
            };
        }

        payload.http_status = response.status;
        return payload;
    }

    function currentFilters() {
        var fd = new FormData(el.form);
        return {
            q: (fd.get('q') || '').toString().trim(),
            make: (fd.get('make') || '').toString().trim(),
            model: (fd.get('model') || '').toString().trim(),
            trim: (fd.get('trim') || '').toString().trim(),
            body_type: (fd.get('body_type') || '').toString().trim(),
            source_type: (fd.get('source_type') || '').toString().trim(),
            state: (fd.get('state') || '').toString().trim().toUpperCase(),
            exterior_color: (fd.get('exterior_color') || '').toString().trim(),
            interior_color: (fd.get('interior_color') || '').toString().trim(),
            drivetrain: (fd.get('drivetrain') || '').toString().trim(),
            fuel_type: (fd.get('fuel_type') || '').toString().trim(),
            transmission: (fd.get('transmission') || '').toString().trim(),
            inventory_type: (fd.get('inventory_type') || '').toString().trim(),
            certified: !!fd.get('certified'),
            single_owner: !!fd.get('single_owner'),
            clean_title: !!fd.get('clean_title'),
            min_dom: (fd.get('min_dom') || '').toString().trim(),
            max_dom: (fd.get('max_dom') || '').toString().trim(),
            min_price: (fd.get('min_price') || '').toString().trim(),
            max_price: (fd.get('max_price') || '').toString().trim(),
            min_year: (fd.get('min_year') || '').toString().trim(),
            max_year: (fd.get('max_year') || '').toString().trim(),
            min_miles: (fd.get('min_miles') || '').toString().trim(),
            max_miles: (fd.get('max_miles') || '').toString().trim(),
            zip_code: (fd.get('zip_code') || '').toString().trim(),
            radius: (fd.get('radius') || '50').toString().trim(),
            has_images: !!fd.get('has_images'),
            live_sync: !!(fd.get('zip_code') || '').toString().trim() && (fd.get('source_type') || '').toString().trim() !== 'auction',
            sort_by: (fd.get('sort_by') || 'updated_at').toString(),
            sort_dir: (fd.get('sort_dir') || 'desc').toString()
        };
    }

    function setSelectOptions(selectId, buckets, config) {
        var select = document.getElementById(selectId);
        if (!select) return;

        var opts = config || {};
        var placeholder = opts.placeholder || 'Any';
        var keepValue = opts.keepValue;
        var previousValue = keepValue !== undefined ? keepValue : select.value;

        var nextOptions = ['<option value="">' + escapeHtml(placeholder) + '</option>'];
        var values = Array.isArray(buckets) ? buckets : [];

        for (var i = 0; i < values.length; i += 1) {
            var bucket = values[i];
            var item = '';
            var count = 0;
            if (bucket && typeof bucket === 'object') {
                item = (bucket.item || '').toString();
                count = Number(bucket.count || 0);
            } else {
                item = (bucket || '').toString();
            }
            item = item.trim();
            if (!item) continue;

            var label = count > 0 ? item + ' (' + count.toLocaleString() + ')' : item;
            nextOptions.push('<option value="' + escapeAttr(item) + '">' + escapeHtml(label) + '</option>');
        }

        select.innerHTML = nextOptions.join('');
        if (previousValue && Array.from(select.options).some(function (opt) { return opt.value === previousValue; })) {
            select.value = previousValue;
        }
    }

    function updateDependentTaxonomyOptions() {
        if (!el.form) return;
        var filters = currentFilters();
        var lookup = (state.taxonomy && state.taxonomy.lookup) || {};
        var modelsByMake = lookup.models_by_make || {};
        var trimsByMakeModel = lookup.trims_by_make_model || {};

        var modelOptions = filters.make ? (modelsByMake[filters.make] || []).map(function (item) {
            return { item: item, count: 0 };
        }) : [];
        setSelectOptions('filterModel', modelOptions, {
            placeholder: filters.make ? 'Select Model' : 'Choose Make First',
            keepValue: filters.model
        });

        var trimKey = filters.make && filters.model ? filters.make + '|||' + filters.model : '';
        var trimOptions = trimKey ? (trimsByMakeModel[trimKey] || []).map(function (item) {
            return { item: item, count: 0 };
        }) : [];
        setSelectOptions('filterTrim', trimOptions, {
            placeholder: 'Any Trim',
            keepValue: filters.trim
        });
    }

    async function loadFacets() {
        var filters = currentFilters();
        var params = new URLSearchParams();

        if (filters.make) params.set('make', filters.make);
        if (filters.model) params.set('model', filters.model);
        if (filters.trim) params.set('trim', filters.trim);
        if (filters.body_type) params.set('body_type', filters.body_type);
        if (filters.state) params.set('state', filters.state);
        if (filters.inventory_type) params.set('inventory_type', filters.inventory_type);
        if (filters.source_type) params.set('source_type', filters.source_type);
        if (filters.min_price) params.set('min_price', filters.min_price);
        if (filters.max_price) params.set('max_price', filters.max_price);
        if (filters.min_year) params.set('min_year', filters.min_year);
        if (filters.max_year) params.set('max_year', filters.max_year);
        if (filters.zip_code) params.set('zip_code', filters.zip_code);
        if (filters.radius) params.set('radius', filters.radius);
        params.set('has_images', filters.has_images ? 'true' : 'false');
        params.set('use_marketcheck', 'false');

        var response = await api('/api/vch/inventory/facets?' + params.toString());
        if (response.status !== 'ok' || !response.data || !response.data.facets) {
            return;
        }

        state.facets = response.data.facets;
        state.taxonomy = response.data.taxonomy || {};

        setSelectOptions('filterMinYear', state.taxonomy.years, {
            placeholder: 'From',
            keepValue: filters.min_year
        });
        setSelectOptions('filterMaxYear', state.taxonomy.years, {
            placeholder: 'To',
            keepValue: filters.max_year
        });

        setSelectOptions('filterMake', state.taxonomy.make || state.facets.make, {
            placeholder: 'Any Make',
            keepValue: filters.make
        });
        updateDependentTaxonomyOptions();
        setSelectOptions('filterBody', state.facets.body_type, {
            placeholder: 'Any Body',
            keepValue: filters.body_type
        });
        setSelectOptions('filterState', state.facets.state, {
            placeholder: 'Any State',
            keepValue: filters.state
        });
        setSelectOptions('filterExteriorColor', state.facets.exterior_color, {
            placeholder: 'Any Exterior',
            keepValue: filters.exterior_color
        });
        setSelectOptions('filterInteriorColor', state.facets.interior_color, {
            placeholder: 'Any Interior',
            keepValue: filters.interior_color
        });
        setSelectOptions('filterDrivetrain', state.facets.drivetrain, {
            placeholder: 'Any Drivetrain',
            keepValue: filters.drivetrain
        });
        setSelectOptions('filterFuelType', state.facets.fuel_type, {
            placeholder: 'Any Fuel',
            keepValue: filters.fuel_type
        });
        setSelectOptions('filterTransmission', state.facets.transmission, {
            placeholder: 'Any Transmission',
            keepValue: filters.transmission
        });
        setSelectOptions('filterInventoryType', state.facets.inventory_type, {
            placeholder: 'Any Condition',
            keepValue: filters.inventory_type
        });
    }

    async function loadInventory(page) {
        var filters = currentFilters();
        var params = new URLSearchParams();

        if (filters.q) params.set('q', filters.q);
        if (filters.make) params.set('make', filters.make);
        if (filters.model) params.set('model', filters.model);
        if (filters.trim) params.set('trim', filters.trim);
        if (filters.body_type) params.set('body_type', filters.body_type);
        if (filters.source_type) params.set('source_type', filters.source_type);
        if (filters.state) params.set('state', filters.state);
        if (filters.exterior_color) params.set('exterior_color', filters.exterior_color);
        if (filters.interior_color) params.set('interior_color', filters.interior_color);
        if (filters.drivetrain) params.set('drivetrain', filters.drivetrain);
        if (filters.fuel_type) params.set('fuel_type', filters.fuel_type);
        if (filters.transmission) params.set('transmission', filters.transmission);
        if (filters.inventory_type) params.set('inventory_type', filters.inventory_type);
        if (filters.certified) params.set('certified', 'true');
        if (filters.single_owner) params.set('single_owner', 'true');
        if (filters.clean_title) params.set('clean_title', 'true');
        if (filters.min_dom) params.set('min_dom', filters.min_dom);
        if (filters.max_dom) params.set('max_dom', filters.max_dom);
        if (filters.min_price) params.set('min_price', filters.min_price);
        if (filters.max_price) params.set('max_price', filters.max_price);
        if (filters.min_year) params.set('min_year', filters.min_year);
        if (filters.max_year) params.set('max_year', filters.max_year);
        if (filters.min_miles) params.set('min_miles', filters.min_miles);
        if (filters.max_miles) params.set('max_miles', filters.max_miles);
        if (filters.zip_code) params.set('zip_code', filters.zip_code);
        if (filters.radius) params.set('radius', filters.radius);
        params.set('has_images', filters.has_images ? 'true' : 'false');
        if (filters.live_sync) {
            params.set('live_sync', 'true');
            params.set('sync_limit', '120');
        }
        params.set('sort_by', filters.sort_by);
        params.set('sort_dir', filters.sort_dir);
        params.set('per_page', '18');
        params.set('page', String(page || 1));

        setError('');
        el.grid.innerHTML = '<div class="vinv-empty">Loading inventory...</div>';

        var response = await api('/api/vch/inventory/search?' + params.toString());
        if (response.status !== 'ok' || !response.data) {
            state.rows = [];
            state.pagination = {
                page: 1,
                per_page: 18,
                total: 0,
                total_pages: 0,
                has_next: false,
                has_prev: false
            };
            setError(response.error && response.error.message ? response.error.message : 'Unable to load inventory');
            renderInventory();
            return;
        }

        state.rows = Array.isArray(response.data.items) ? response.data.items : [];
        state.pagination = response.data.pagination || state.pagination;
        state.sync = response.data.sync || null;
        renderInventory();
    }

    function renderInventory() {
        var total = Number(state.pagination.total || 0);
        var page = Number(state.pagination.page || 1);
        var totalPages = Number(state.pagination.total_pages || 0);

        if (el.resultCount) {
            el.resultCount.textContent = total.toLocaleString() + ' listings | Page ' + page + ' of ' + Math.max(totalPages, 1);
        }

        if (el.syncBadge) {
            if (state.sync && state.sync.requested) {
                var synced = Array.isArray(state.sync.synced_vins) ? state.sync.synced_vins.length : 0;
                el.syncBadge.textContent =
                    'Sync ' + (state.sync.mode || 'unknown') +
                    ' | +' + (state.sync.inserted || 0) +
                    ' new / ' + (state.sync.updated || 0) +
                    ' updated / ' + synced + ' filtered';
            } else if (!currentFilters().zip_code) {
                el.syncBadge.textContent = 'Local Search | Add ZIP for MarketCheck';
            } else {
                el.syncBadge.textContent = 'Local Search';
            }
        }

        renderActiveFilters();

        if (!state.rows.length) {
            el.grid.innerHTML = '<div class="vinv-empty">No vehicles match your filters.</div>';
        } else {
            el.grid.innerHTML = state.rows.map(renderCard).join('');
        }

        renderPagination();
    }

    function renderActiveFilters() {
        if (!el.activeFilters) return;

        var filters = currentFilters();
        var chips = [];

        if (filters.q) chips.push({ label: 'Search', value: filters.q });
        if (filters.make) chips.push({ label: 'Make', value: filters.make });
        if (filters.model) chips.push({ label: 'Model', value: filters.model });
        if (filters.trim) chips.push({ label: 'Trim', value: filters.trim });
        if (filters.body_type) chips.push({ label: 'Body', value: filters.body_type });
        if (filters.inventory_type) chips.push({ label: 'Condition', value: filters.inventory_type });
        if (filters.source_type) chips.push({ label: 'Source', value: filters.source_type });
        if (filters.fuel_type) chips.push({ label: 'Fuel', value: filters.fuel_type });
        if (filters.transmission) chips.push({ label: 'Transmission', value: filters.transmission });
        if (filters.drivetrain) chips.push({ label: 'Drive', value: filters.drivetrain });
        if (filters.state) chips.push({ label: 'State', value: filters.state });
        if (filters.zip_code) chips.push({ label: 'ZIP', value: filters.zip_code });
        if (filters.radius) chips.push({ label: 'Radius', value: filters.radius + ' miles' });
        if (filters.exterior_color) chips.push({ label: 'Exterior', value: filters.exterior_color });
        if (filters.interior_color) chips.push({ label: 'Interior', value: filters.interior_color });

        if (filters.min_price || filters.max_price) {
            chips.push({
                label: 'Price',
                value: [
                    filters.min_price ? formatMoney(filters.min_price) : 'Any',
                    filters.max_price ? formatMoney(filters.max_price) : 'Any'
                ].join(' - ')
            });
        }

        if (filters.min_year || filters.max_year) {
            chips.push({
                label: 'Year',
                value: [
                    filters.min_year || 'Any',
                    filters.max_year || 'Any'
                ].join(' - ')
            });
        }

        if (filters.min_miles || filters.max_miles) {
            chips.push({
                label: 'Miles',
                value: [
                    filters.min_miles ? formatNumber(filters.min_miles) : 'Any',
                    filters.max_miles ? formatNumber(filters.max_miles) : 'Any'
                ].join(' - ')
            });
        }

        el.activeFilters.innerHTML = chips.map(function (chip) {
            return '<span class="vinv-filter-chip"><strong>' + escapeHtml(chip.label) + ':</strong> ' + escapeHtml(formatFilterValue(chip.label, chip.value)) + '</span>';
        }).join('');
    }

    function renderCard(item) {
        var title = ((item.year || '') + ' ' + (item.make || '') + ' ' + (item.model || '')).trim();
        var inGarage = state.garage.some(function (g) { return g.vin === item.vin; });
        var auctionListing = isAuctionItem(item);
        var badgeLabel = auctionListing ? 'Auction' : titleCase(item.inventory_type || (item.certified ? 'certified' : 'used') || 'listing');
        var subtitleBits = [];
        var imageCount = Array.isArray(item.images) ? item.images.length : Number(item.images_count || 0);
        var marketLabel = item.source_label || (auctionListing ? 'Auction' : 'Inventory');
        if (item.trim) subtitleBits.push(item.trim);
        if (item.body_type) subtitleBits.push(item.body_type);
        if (item.drivetrain) subtitleBits.push(item.drivetrain);
        else if (item.transmission) subtitleBits.push(item.transmission);

        return [
            '<article class="vinv-listing-card">',
            '  <div class="vinv-listing-media">',
            '    <img class="vinv-card-media" src="' + escapeAttr(fallbackImageFor(item)) + '" alt="' + escapeAttr(title || item.vin) + '">',
            '    <span class="vinv-listing-badge' + (auctionListing ? ' auction' : '') + '">' + escapeHtml(badgeLabel) + '</span>',
            '    <button class="vinv-listing-media-button" type="button" data-action="detail" data-vin="' + escapeAttr(item.vin) + '"><i class="fa-regular fa-images"></i> ' + imageCount + ' Photos</button>',
            '  </div>',
            '  <div class="vinv-listing-body">',
            '    <div class="vinv-listing-top">',
            '      <div>',
            '        <h3 class="vinv-listing-title">' + escapeHtml(title || item.vin) + '</h3>',
            '        <p class="vinv-listing-subtitle">' + escapeHtml(subtitleBits.join(' | ') || 'Vehicle details pending') + '</p>',
            '        <p class="vinv-listing-meta">' + escapeHtml(marketLabel) + ' | VIN ' + escapeHtml(item.vin) + '</p>',
            '      </div>',
            '      <div class="vinv-listing-price">',
            '        <strong>' + formatMoney(item.price_asking) + '</strong>',
            '        <small>' + escapeHtml((item.location_state || 'NA') + (item.location_zip ? ' ' + item.location_zip : '')) + '</small>',
            '      </div>',
            '    </div>',
            '    <div class="vinv-specs">',
            '      <div class="vinv-spec"><i class="fa-solid fa-car-side"></i><div><span>' + escapeHtml(item.body_type || 'Vehicle') + '</span></div></div>',
            '      <div class="vinv-spec"><i class="fa-regular fa-calendar"></i><div><span>' + escapeHtml(String(item.year || 'N/A')) + '</span></div></div>',
            '      <div class="vinv-spec"><i class="fa-solid fa-gears"></i><div><span>' + escapeHtml(item.transmission || 'Automatic') + '</span></div></div>',
            '      <div class="vinv-spec"><i class="fa-solid fa-gas-pump"></i><div><span>' + escapeHtml(item.fuel_type || item.engine_type || 'N/A') + '</span></div></div>',
            '      <div class="vinv-spec"><i class="fa-solid fa-gauge-high"></i><div><span>' + escapeHtml(formatNumber(item.odometer)) + ' mi</span></div></div>',
            '    </div>',
            '    <div class="vinv-listing-actions">',
            '      <div class="vinv-listing-buttons">',
            '        <button class="vinv-btn vinv-btn-secondary" type="button" data-action="garage" data-vin="' + escapeAttr(item.vin) + '">' + (inGarage ? 'Saved in My Garage' : 'Add to My Garage') + '</button>',
            auctionListing ? '        <button class="vinv-btn vinv-btn-secondary" type="button" data-action="condition-report" data-vin="' + escapeAttr(item.vin) + '">Condition report</button>' : '',
            '        <button class="vinv-btn vinv-btn-secondary" type="button" data-action="detail" data-vin="' + escapeAttr(item.vin) + '">View details</button>',
            '      </div>',
            '    </div>',
            '  </div>',
            '</article>'
        ].join('');
    }

    function renderPagination() {
        var p = state.pagination || {};
        if (!p.total_pages || p.total_pages <= 1) {
            if (el.paginationTop) el.paginationTop.innerHTML = '';
            el.pagination.innerHTML = '';
            return;
        }

        var current = Number(p.page || 1);
        var totalPages = Number(p.total_pages || 1);
        var start = Math.max(1, current - 2);
        var end = Math.min(totalPages, current + 2);

        var html = '<div class="vinv-paginate">';
        html += '<button class="vinv-btn vinv-btn-secondary" data-page="' + Math.max(current - 1, 1) + '" ' + (p.has_prev ? '' : 'disabled') + '>Previous</button>';
        for (var i = start; i <= end; i += 1) {
            html += '<button class="' + (i === current ? 'vinv-btn vinv-btn-primary' : 'vinv-btn vinv-btn-secondary') + '" data-page="' + i + '">' + i + '</button>';
        }
        html += '<button class="vinv-btn vinv-btn-secondary" data-page="' + (current + 1) + '" ' + (p.has_next ? '' : 'disabled') + '>Next</button>';
        html += '</div>';

        if (el.paginationTop) el.paginationTop.innerHTML = html;
        el.pagination.innerHTML = html;
    }

    async function loadVehicleDetail(vin) {
        if (state.detailCache[vin]) {
            return state.detailCache[vin];
        }
        var response = await api('/api/vch/inventory/' + encodeURIComponent(vin));
        if (response.status !== 'ok' || !response.data) {
            throw new Error(response.error && response.error.message ? response.error.message : 'Unable to load vehicle detail');
        }
        state.detailCache[vin] = response.data;
        return response.data;
    }

    async function openDetail(vin) {
        try {
            var vehicle = await loadVehicleDetail(vin);
            state.modalVehicle = vehicle;
            var displayImages = vehicle.display_images || vehicle.images || [];
            state.modalImage = displayImages[0] || vehicle.hero_image || fallbackImageFor(vehicle);
            renderModal();
            el.modal.classList.add('open');
        } catch (error) {
            setError(error.message || 'Unable to open details');
        }
    }

    function closeModal() {
        el.modal.classList.remove('open');
        state.modalVehicle = null;
        state.modalImage = null;
        el.modalBody.innerHTML = '';
    }

    function openAuthPrompt(message, pendingAction) {
        state.pendingAction = pendingAction || state.pendingAction;
        if (el.authPromptMessage) {
            el.authPromptMessage.textContent = message || 'To Use My Garage Create Free account or Login';
        }
        if (el.authPromptEmail) {
            el.authPromptEmail.value = (state.auth && state.auth.email) || (el.authEmail && el.authEmail.value) || '';
        }
        if (el.authPromptPassword) {
            el.authPromptPassword.value = '';
        }
        setAuthPromptStatus('', false);
        if (el.authPromptModal) {
            el.authPromptModal.classList.add('open');
        }
    }

    function closeAuthPrompt() {
        if (el.authPromptModal) {
            el.authPromptModal.classList.remove('open');
        }
        setAuthPromptStatus('', false);
    }

    async function resumePendingAction() {
        var pending = state.pendingAction;
        state.pendingAction = null;
        if (!pending || !pending.vin) return;
        if (pending.type === 'garage') {
            await addGarage(pending.vin, { skipPrompt: true });
        } else if (pending.type === 'acquire') {
            await startAcquisition(pending.vin, { skipPrompt: true });
        } else if (pending.type === 'condition-report') {
            await requestConditionReport(pending.vin, { skipPrompt: true });
        }
    }

    async function authFromPrompt(mode) {
        var email = (el.authPromptEmail && el.authPromptEmail.value || '').trim();
        var password = (el.authPromptPassword && el.authPromptPassword.value || '').trim();

        if (!email || !password) {
            setAuthPromptStatus('Email and password are required.', true);
            return;
        }

        setAuthPromptStatus(mode === 'register' ? 'Creating account...' : 'Signing in...', false);

        var endpoint = mode === 'register' ? '/api/vch/auth/register' : '/api/vch/auth/login';
        var response = await api(endpoint, {
            method: 'POST',
            body: { email: email, password: password }
        });

        if (response.status !== 'ok' || !response.data || !response.data.access_token) {
            setAuthPromptStatus(response.error && response.error.message ? response.error.message : 'Authentication failed', true);
            return;
        }

        saveAuth({
            email: email,
            user_id: response.data.user_id,
            access_token: response.data.access_token,
            refresh_token: response.data.refresh_token
        });

        if (el.authEmail) el.authEmail.value = email;
        if (el.authPassword) el.authPassword.value = password;

        closeAuthPrompt();
        await Promise.all([loadDeal(), loadGarage()]);
        renderInventory();
        await resumePendingAction();
    }

    async function requireAuth(action) {
        if (state.auth && state.auth.access_token) return state.auth;
        openAuthPrompt('To Use My Garage Create Free account or Login', action || null);
        return null;
    }

    function isAuthFailure(response) {
        var code = Number(response && response.http_status || 0);
        return code === 401 || code === 403;
    }

    async function loadDeal() {
        if (!state.auth || !state.auth.access_token) {
            state.deal = null;
            setDealBadge();
            return;
        }
        var response = await api('/api/vch/me/deal', { token: state.auth.access_token });
        if (response.status === 'ok') {
            state.deal = response.data;
        } else {
            state.deal = null;
            if (isAuthFailure(response)) clearAuth();
        }
        setDealBadge();
    }

    async function loadGarage() {
        if (!state.auth || !state.auth.access_token) {
            state.garage = [];
            renderGarage();
            return;
        }

        var response = await api('/api/vch/me/garage', { token: state.auth.access_token });
        if (response.status === 'ok' && Array.isArray(response.data)) {
            state.garage = response.data;
        } else {
            if (isAuthFailure(response)) {
                clearAuth();
                openAuthPrompt('Your session expired. To Use My Garage Create Free account or Login');
            }
            state.garage = [];
        }
        renderGarage();
    }

    async function addGarage(vin, options) {
        var opts = options || {};
        var auth = opts.skipPrompt && state.auth && state.auth.access_token ? state.auth : await requireAuth({ type: 'garage', vin: vin });
        if (!auth) return;

        var response = await api('/api/vch/me/garage/' + encodeURIComponent(vin), {
            method: 'POST',
            token: auth.access_token
        });

        if (response.status !== 'ok') {
            if (isAuthFailure(response)) {
                clearAuth();
                openAuthPrompt('To Use My Garage Create Free account or Login', { type: 'garage', vin: vin });
                return;
            }
            setError(response.error && response.error.message ? response.error.message : 'Unable to add to garage');
            return;
        }

        setError('');
        await loadGarage();
        renderInventory();
    }

    async function removeGarage(vin) {
        var auth = await requireAuth({ type: 'garage', vin: vin });
        if (!auth) return;

        var response = await api('/api/vch/me/garage/' + encodeURIComponent(vin), {
            method: 'DELETE',
            token: auth.access_token
        });

        if (response.status !== 'ok') {
            if (isAuthFailure(response)) {
                clearAuth();
                openAuthPrompt('To Use My Garage Create Free account or Login', { type: 'garage', vin: vin });
                return;
            }
            setError(response.error && response.error.message ? response.error.message : 'Unable to remove from garage');
            return;
        }

        setError('');
        await loadGarage();
        renderInventory();
    }

    async function startAcquisition(vin, options) {
        var opts = options || {};
        var auth = opts.skipPrompt && state.auth && state.auth.access_token ? state.auth : await requireAuth({ type: 'acquire', vin: vin });
        if (!auth) return;

        var response = await api('/api/vch/me/garage/' + encodeURIComponent(vin) + '/acquire', {
            method: 'POST',
            token: auth.access_token
        });

        if (response.status !== 'ok') {
            if (isAuthFailure(response)) {
                clearAuth();
                openAuthPrompt('To Use My Garage Create Free account or Login', { type: 'acquire', vin: vin });
                return;
            }
            setError(response.error && response.error.message ? response.error.message : 'Unable to start acquisition');
            return;
        }

        setError('');
        await Promise.all([loadGarage(), loadDeal()]);
        renderInventory();
        closeModal();
    }

    async function requestConditionReport(vin, options) {
        var opts = options || {};
        var auth = opts.skipPrompt && state.auth && state.auth.access_token ? state.auth : await requireAuth({ type: 'condition-report', vin: vin });
        if (!auth) return;

        if (!state.deal) {
            await loadDeal();
        }

        if (!dealAllowsConditionReport()) {
            var eligibilityMessage = conditionReportEligibilityMessage();
            setError(eligibilityMessage);
            window.alert(eligibilityMessage);
            return;
        }

        var response = await api('/api/vch/me/vehicles/' + encodeURIComponent(vin) + '/condition-report-request', {
            method: 'POST',
            token: auth.access_token
        });

        if (response.status !== 'ok') {
            if (isAuthFailure(response)) {
                clearAuth();
                openAuthPrompt('Log in with your buyer account to request a VCH condition report.', { type: 'condition-report', vin: vin });
                return;
            }

            var errorMessage = response.error && response.error.message
                ? response.error.message
                : 'Unable to request condition report';
            setError(errorMessage);
            if (response.http_status === 403) {
                window.alert(errorMessage);
            }
            return;
        }

        setError('');
        state.detailCache[vin] = null;
        window.alert(
            response.data && response.data.message
                ? response.data.message
                : 'Condition report requested.'
        );
        if (response.data && response.data.already_available) {
            await openDetail(vin);
        }
    }

    function renderGarage() {
        if (!el.garageList) {
            if (el.garageCount) {
                el.garageCount.textContent = state.garage.length + ' saved';
            }
            return;
        }

        if (el.garageCount) {
            el.garageCount.textContent = state.garage.length + ' saved';
        }

        if (!state.garage.length) {
            el.garageList.innerHTML = '<div class="vinv-empty">No saved vehicles yet.</div>';
            return;
        }

        el.garageList.innerHTML = state.garage.map(function (item) {
            var v = item.vehicle || {};
            var title = ((v.year || '') + ' ' + (v.make || '') + ' ' + (v.model || '')).trim() || item.vin;
            return [
                '<div class="vinv-garage-item">',
                '<p><strong>' + escapeHtml(title) + '</strong></p>',
                '<p>' + formatMoney(v.price_asking) + ' | ' + escapeHtml(v.location_state || 'NA') + ' ' + escapeHtml(v.location_zip || '') + '</p>',
                '<p>VIN: ' + escapeHtml(item.vin) + ' | Status: ' + escapeHtml(item.status || 'saved') + '</p>',
                '<div class="vinv-actions" style="margin-top:8px;">',
                '<button class="vinv-btn vinv-btn-secondary" data-garage-action="open" data-vin="' + escapeAttr(item.vin) + '">Open</button>',
                '<button class="vinv-btn vinv-btn-primary" data-garage-action="acquire" data-vin="' + escapeAttr(item.vin) + '">Start Acquisition</button>',
                '<button class="vinv-btn vinv-btn-secondary" data-garage-action="remove" data-vin="' + escapeAttr(item.vin) + '">Remove</button>',
                '</div>',
                '</div>'
            ].join('');
        }).join('');
    }

    function renderModal() {
        var v = state.modalVehicle;
        if (!v) {
            el.modalBody.innerHTML = '';
            return;
        }

        var title = ((v.year || '') + ' ' + (v.make || '') + ' ' + (v.model || '')).trim();
        var displayImages = v.display_images || v.images || [];
        var auctionListing = isAuctionItem(v);
        var image = state.modalImage || displayImages[0] || fallbackImageFor(v);
        var thumbs = displayImages.slice(0, 20).map(function (url) {
            return '<img class="vinv-thumb" src="' + escapeAttr(url) + '" alt="thumb" data-thumb="' + escapeAttr(url) + '">';
        }).join('');

        var features = (v.features_full || v.features_raw || []).slice(0, 60).map(function (f) {
            return '<span class="vinv-feature">' + escapeHtml(f) + '</span>';
        }).join('');

        var badges = [];
        if (v.inventory_type) badges.push('<span class="vinv-pill">' + escapeHtml(String(v.inventory_type).toUpperCase()) + '</span>');
        if (v.certified) badges.push('<span class="vinv-pill">CERTIFIED</span>');
        if (v.single_owner) badges.push('<span class="vinv-pill">1 OWNER</span>');
        if (v.clean_title) badges.push('<span class="vinv-pill">CLEAN TITLE</span>');
        if (v.source_label) badges.push('<span class="vinv-pill">' + escapeHtml(String(v.source_label).toUpperCase()) + '</span>');

        var description = v.description ? '<p class="vinv-modal-description">' + escapeHtml(v.description) + '</p>' : '<p class="vinv-text">Listing description not provided by source.</p>';
        var reportSummary = '';
        if (auctionListing && hasConditionReport(v)) {
            reportSummary = '<p class="vinv-text">VCH condition report is available for this auction listing.</p>';
        } else if (auctionListing) {
            reportSummary = '<p class="vinv-text">This auction listing is showing a placeholder image until a VCH condition report is ordered and synced.</p>';
        }

        var odometerText = formatNumber(v.odometer) + ' ' + escapeHtml(v.odometer_units || 'mi');
        var sellerComments = v.seller_comments
            ? '<div class="vinv-modal-panel"><h4>Seller Comments</h4><p>' + escapeHtml(v.seller_comments) + '</p></div>'
            : '';
        var auctionMeta = [
            { label: 'VIN', value: v.vin },
            { label: 'Year', value: v.year },
            { label: 'Make', value: v.make },
            { label: 'Model', value: v.model },
            { label: 'Trim', value: v.trim || 'Base' },
            { label: 'Exterior Color', value: v.exterior_color || 'N/A' },
            { label: 'Interior Color', value: v.interior_color || 'N/A' },
            { label: 'Odometer', value: odometerText },
            { label: 'Drivetrain', value: v.drivetrain || 'N/A' },
            { label: 'Transmission', value: v.transmission_type || v.transmission || 'N/A' },
            { label: 'Engine', value: v.engine_type || v.fuel_type || 'N/A' },
            { label: 'MMR', value: v.mmr ? formatMoney(v.mmr) : 'N/A' },
            { label: 'Condition Grade', value: v.condition_report_grade || v.condition_grade || 'N/A' },
            { label: 'Pickup Location', value: v.pickup_location || 'N/A' },
            { label: 'Auction House', value: v.auction_house || 'N/A' },
            { label: 'Auction Status', value: v.inventory_status || v.inventory_label || 'N/A' }
        ].map(function (row) {
            return '<div class="vinv-modal-data-row"><span>' + escapeHtml(row.label) + '</span><strong>' + escapeHtml(String(row.value)) + '</strong></div>';
        }).join('');

        el.modalBody.innerHTML = [
            '<div class="vinv-modal-content">',
            '  <div>',
            '    <img class="vinv-modal-main-image" src="' + escapeAttr(image) + '" alt="' + escapeAttr(title) + '">',
            '    <div class="vinv-thumb-row">' + thumbs + '</div>',
            '  </div>',
            '  <div class="vinv-modal-info">',
            '    <h3>' + escapeHtml(title || v.vin) + '</h3>',
            '    <div class="vinv-meta">' + badges.join('') + '</div>',
            '    <p class="vinv-price">' + formatMoney(v.price_asking) + '</p>',
            '    <div class="vinv-modal-panel">',
            '      <h4>Vehicle Details</h4>',
            '      <div class="vinv-modal-data-grid">' + auctionMeta + '</div>',
            '    </div>',
            description,
            reportSummary,
            sellerComments,
            '    <div class="vinv-feature-wrap">' + (features || '<span class="vinv-feature">No listed features</span>') + '</div>',
            '    <div class="vinv-actions">',
            '      <button class="vinv-btn vinv-btn-primary" data-modal-action="garage" data-vin="' + escapeAttr(v.vin) + '">Add to My Garage</button>',
            auctionListing ? '      <button class="vinv-btn vinv-btn-secondary" data-modal-action="condition-report" data-vin="' + escapeAttr(v.vin) + '">' + (hasConditionReport(v) ? 'Refresh Condition Report' : 'Order Condition Report') + '</button>' : '',
            '      <button class="vinv-btn vinv-btn-secondary" data-modal-action="acquire" data-vin="' + escapeAttr(v.vin) + '">Start Acquisition</button>',
            '    </div>',
            '  </div>',
            '</div>'
        ].join('');
    }

    async function onLogin() {
        var email = (el.authEmail && el.authEmail.value || '').trim();
        var password = (el.authPassword && el.authPassword.value || '').trim();
        if (!email || !password) {
            setStatus('Email and password are required.', true);
            return;
        }

        setStatus('Signing in...', false);
        var response = await api('/api/vch/auth/login', {
            method: 'POST',
            body: { email: email, password: password }
        });

        if (response.status !== 'ok' || !response.data || !response.data.access_token) {
            setStatus(response.error && response.error.message ? response.error.message : 'Sign in failed', true);
            return;
        }

        saveAuth({
            email: email,
            user_id: response.data.user_id,
            access_token: response.data.access_token,
            refresh_token: response.data.refresh_token
        });

        await Promise.all([loadDeal(), loadGarage()]);
        renderInventory();
    }

    function bindEvents() {
        if (el.authLoginBtn) {
            el.authLoginBtn.addEventListener('click', onLogin);
        }

        if (el.authLogoutBtn) {
            el.authLogoutBtn.addEventListener('click', function () {
                clearAuth();
                closeAuthPrompt();
            });
        }

        if (el.form) {
            el.form.addEventListener('submit', function (event) {
                event.preventDefault();
                saveSearchContext();
                loadFacets().then(function () {
                    loadInventory(1);
                });
            });

            el.form.addEventListener('change', function (event) {
                var target = event.target;
                if (!target || !target.name) return;

                if (target.name === 'zip_code' || target.name === 'radius') {
                    saveSearchContext();
                }

                if (target.name === 'make') {
                    var modelSelect = el.form.querySelector('select[name="model"]');
                    var trimSelect = el.form.querySelector('select[name="trim"]');
                    if (modelSelect) modelSelect.value = '';
                    if (trimSelect) trimSelect.value = '';
                    updateDependentTaxonomyOptions();
                    return;
                }

                if (target.name === 'model') {
                    var nextTrimSelect = el.form.querySelector('select[name="trim"]');
                    if (nextTrimSelect) nextTrimSelect.value = '';
                    updateDependentTaxonomyOptions();
                }
            });

            var zipInput = el.form.querySelector('input[name="zip_code"]');
            if (zipInput) {
                zipInput.addEventListener('blur', function () {
                    saveSearchContext();
                });
            }
        }

        if (el.resetBtn) {
            el.resetBtn.addEventListener('click', function () {
                if (!el.form) return;
                el.form.reset();

                var hasImages = el.form.querySelector('input[name="has_images"]');
                var liveSync = el.form.querySelector('input[name="live_sync"]');
                var sortBy = el.form.querySelector('select[name="sort_by"]');
                var sortDir = el.form.querySelector('select[name="sort_dir"]');

                if (hasImages) hasImages.checked = false;
                if (liveSync) liveSync.checked = true;
                if (sortBy) sortBy.value = 'updated_at';
                if (sortDir) sortDir.value = 'desc';

                updateDependentTaxonomyOptions();
                loadFacets().then(function () {
                    loadInventory(1);
                });
            });
        }

        if (el.grid) {
            el.grid.addEventListener('click', async function (event) {
                var btn = event.target.closest('[data-action]');
                if (!btn) return;
                event.preventDefault();
                var action = btn.getAttribute('data-action');
                var vin = btn.getAttribute('data-vin');
                if (!action || !vin) return;

                if (action === 'detail') {
                    await openDetail(vin);
                } else if (action === 'condition-report') {
                    await requestConditionReport(vin);
                } else if (action === 'garage') {
                    var inGarage = state.garage.some(function (g) { return g.vin === vin; });
                    if (inGarage) return;
                    await addGarage(vin);
                }
            });
        }

        if (el.pagination) {
            el.pagination.addEventListener('click', function (event) {
                var btn = event.target.closest('button[data-page]');
                if (!btn || btn.disabled) return;
                var page = Number(btn.getAttribute('data-page') || '1');
                loadInventory(page);
            });
        }

        if (el.paginationTop) {
            el.paginationTop.addEventListener('click', function (event) {
                var btn = event.target.closest('button[data-page]');
                if (!btn || btn.disabled) return;
                var page = Number(btn.getAttribute('data-page') || '1');
                loadInventory(page);
            });
        }

        if (el.garageList) {
            el.garageList.addEventListener('click', async function (event) {
                var btn = event.target.closest('button');
                if (!btn) return;
                var action = btn.getAttribute('data-garage-action');
                var vin = btn.getAttribute('data-vin');
                if (!action || !vin) return;

                if (action === 'open') {
                    await openDetail(vin);
                } else if (action === 'acquire') {
                    await startAcquisition(vin);
                } else if (action === 'remove') {
                    await removeGarage(vin);
                }
            });
        }

        if (el.modalClose) {
            el.modalClose.addEventListener('click', closeModal);
        }

        if (el.modal) {
            el.modal.addEventListener('click', function (event) {
                if (event.target === el.modal) closeModal();
            });
        }

        if (el.modalBody) {
            el.modalBody.addEventListener('click', async function (event) {
                var thumb = event.target.closest('[data-thumb]');
                if (thumb && state.modalVehicle) {
                    state.modalImage = thumb.getAttribute('data-thumb');
                    renderModal();
                    return;
                }

                var btn = event.target.closest('button[data-modal-action]');
                if (!btn) return;
                var action = btn.getAttribute('data-modal-action');
                var vin = btn.getAttribute('data-vin');
                if (!action || !vin) return;

                if (action === 'garage') {
                    await addGarage(vin);
                } else if (action === 'condition-report') {
                    await requestConditionReport(vin);
                } else if (action === 'acquire') {
                    await startAcquisition(vin);
                }
            });
        }

        if (el.authPromptClose) {
            el.authPromptClose.addEventListener('click', function () {
                closeAuthPrompt();
            });
        }

        if (el.authPromptModal) {
            el.authPromptModal.addEventListener('click', function (event) {
                if (event.target === el.authPromptModal) closeAuthPrompt();
            });
        }

        if (el.authPromptLogin) {
            el.authPromptLogin.addEventListener('click', function () {
                authFromPrompt('login');
            });
        }

        if (el.authPromptRegister) {
            el.authPromptRegister.addEventListener('click', function () {
                authFromPrompt('register');
            });
        }

        if (el.authPromptPassword) {
            el.authPromptPassword.addEventListener('keydown', function (event) {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    authFromPrompt('login');
                }
            });
        }

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                closeModal();
                closeAuthPrompt();
            }
        });
    }

    function formatMoney(value) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return 'N/A';
        return '$' + Number(value).toLocaleString();
    }

    function formatNumber(value) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return 'N/A';
        return Number(value).toLocaleString();
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function escapeAttr(value) {
        return escapeHtml(value);
    }

    async function init() {
        bindEvents();
        restoreSearchContext();

        var auth = loadAuth();
        if (auth && auth.access_token) {
            saveAuth(auth);
            await Promise.all([loadDeal(), loadGarage()]);
        } else {
            clearAuth();
        }

        await loadFacets();
        await loadInventory(1);
    }

    init();
})();
