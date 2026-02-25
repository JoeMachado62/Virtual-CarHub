(function () {
    const AUTH_KEY = 'vch_auth_session';

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
        pagination: document.getElementById('vinvPagination'),
        error: document.getElementById('vinvError'),
        resultCount: document.getElementById('vinvResultCount'),
        syncBadge: document.getElementById('vinvSyncBadge'),

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
            has_images: !!fd.get('has_images'),
            live_sync: !!fd.get('live_sync'),
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

    async function loadFacets() {
        var filters = currentFilters();
        var params = new URLSearchParams();

        if (filters.make) params.set('make', filters.make);
        if (filters.model) params.set('model', filters.model);
        if (filters.body_type) params.set('body_type', filters.body_type);
        if (filters.state) params.set('state', filters.state);
        if (filters.inventory_type) params.set('inventory_type', filters.inventory_type);
        if (filters.min_price) params.set('min_price', filters.min_price);
        if (filters.max_price) params.set('max_price', filters.max_price);
        if (filters.min_year) params.set('min_year', filters.min_year);
        if (filters.max_year) params.set('max_year', filters.max_year);
        params.set('has_images', filters.has_images ? 'true' : 'false');
        params.set('use_marketcheck', 'true');

        var response = await api('/api/vch/inventory/facets?' + params.toString());
        if (response.status !== 'ok' || !response.data || !response.data.facets) {
            return;
        }

        state.facets = response.data.facets;

        setSelectOptions('filterMake', state.facets.make, {
            placeholder: 'Any Make',
            keepValue: filters.make
        });
        setSelectOptions('filterModel', state.facets.model, {
            placeholder: filters.make ? 'Select Model' : 'Choose Make First',
            keepValue: filters.model
        });
        setSelectOptions('filterTrim', state.facets.trim, {
            placeholder: 'Any Trim',
            keepValue: filters.trim
        });
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
        if (filters.has_images) params.set('has_images', 'true');
        if (filters.live_sync) {
            params.set('live_sync', 'true');
            params.set('sync_limit', '120');
        }
        params.set('sort_by', filters.sort_by);
        params.set('sort_dir', filters.sort_dir);
        params.set('per_page', '18');
        params.set('page', String(page || 1));

        setError('');
        el.grid.innerHTML = '<div class="col-12"><div class="vinv-empty">Loading inventory...</div></div>';

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
            } else {
                el.syncBadge.textContent = 'Local Search';
            }
        }

        if (!state.rows.length) {
            el.grid.innerHTML = '<div class="col-12"><div class="vinv-empty">No vehicles match your filters.</div></div>';
        } else {
            el.grid.innerHTML = state.rows.map(renderCard).join('');
        }

        renderPagination();
    }

    function renderCard(item) {
        var title = ((item.year || '') + ' ' + (item.make || '') + ' ' + (item.model || '')).trim();
        var inGarage = state.garage.some(function (g) { return g.vin === item.vin; });
        var condition = item.inventory_type || (item.certified ? 'certified' : 'used');
        var dom = item.days_on_market !== null && item.days_on_market !== undefined ? item.days_on_market + ' DOM' : 'DOM N/A';

        return [
            '<div class="col-lg-4 col-md-6 col-sm-12">',
            '  <article class="vinv-card">',
            '    <img class="vinv-card-media" src="' + escapeAttr(item.thumbnail || '/assets/images/portfolio/01.webp') + '" alt="' + escapeAttr(title) + '">',
            '    <div class="vinv-card-body">',
            '      <div class="vinv-card-top">',
            '        <h5 class="vinv-car-name">' + escapeHtml(title || item.vin) + '</h5>',
            '        <span class="vinv-pill">' + escapeHtml((condition || 'listing').toString().toUpperCase()) + '</span>',
            '      </div>',
            '      <p class="vinv-price">' + formatMoney(item.price_asking) + '</p>',
            '      <p class="vinv-text">' + escapeHtml(item.trim || 'Base') + ' | ' + escapeHtml(item.body_type || 'Vehicle') + ' | ' + escapeHtml(item.drivetrain || item.transmission || 'N/A') + '</p>',
            '      <p class="vinv-text">' + formatNumber(item.odometer) + ' miles | ' + escapeHtml(item.location_state || 'NA') + ' ' + escapeHtml(item.location_zip || '') + '</p>',
            '      <p class="vinv-text">' + escapeHtml(item.exterior_color || item.interior_color || 'Color not listed') + ' | ' + escapeHtml(dom) + '</p>',
            '      <p class="vinv-text">VIN: ' + escapeHtml(item.vin) + '</p>',
            '      <div class="vinv-card-actions">',
            '        <button class="vinv-btn" data-action="detail" data-vin="' + escapeAttr(item.vin) + '">View</button>',
            '        <button class="vinv-btn-ghost" data-action="garage" data-vin="' + escapeAttr(item.vin) + '">' + (inGarage ? 'In Garage' : 'Add to My Garage') + '</button>',
            '      </div>',
            '    </div>',
            '  </article>',
            '</div>'
        ].join('');
    }

    function renderPagination() {
        var p = state.pagination || {};
        if (!p.total_pages || p.total_pages <= 1) {
            el.pagination.innerHTML = '';
            return;
        }

        var current = Number(p.page || 1);
        var totalPages = Number(p.total_pages || 1);
        var start = Math.max(1, current - 2);
        var end = Math.min(totalPages, current + 2);

        var html = '<div class="vinv-paginate">';
        html += '<button class="vinv-btn-ghost" data-page="' + Math.max(current - 1, 1) + '" ' + (p.has_prev ? '' : 'disabled') + '>Previous</button>';
        for (var i = start; i <= end; i += 1) {
            html += '<button class="' + (i === current ? 'vinv-btn' : 'vinv-btn-ghost') + '" data-page="' + i + '">' + i + '</button>';
        }
        html += '<button class="vinv-btn-ghost" data-page="' + (current + 1) + '" ' + (p.has_next ? '' : 'disabled') + '>Next</button>';
        html += '</div>';

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
            state.modalImage = displayImages[0] || vehicle.hero_image || '/assets/images/portfolio/01.webp';
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

    function renderGarage() {
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
                '<button class="vinv-btn-ghost" data-garage-action="open" data-vin="' + escapeAttr(item.vin) + '">Open</button>',
                '<button class="vinv-btn" data-garage-action="acquire" data-vin="' + escapeAttr(item.vin) + '">Start Acquisition</button>',
                '<button class="vinv-btn-ghost" data-garage-action="remove" data-vin="' + escapeAttr(item.vin) + '">Remove</button>',
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
        var image = state.modalImage || displayImages[0] || '/assets/images/portfolio/01.webp';
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

        var description = v.description ? '<p class="vinv-modal-description">' + escapeHtml(v.description) + '</p>' : '<p class="vinv-text">Listing description not provided by source.</p>';

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
            '    <p>VIN: ' + escapeHtml(v.vin) + '</p>',
            '    <p>' + escapeHtml(v.trim || 'Base') + ' | ' + escapeHtml(v.body_type || 'Vehicle') + ' | ' + escapeHtml(v.drivetrain || 'N/A') + '</p>',
            '    <p>' + formatNumber(v.odometer) + ' miles | ' + escapeHtml(v.city || '') + (v.city ? ', ' : '') + escapeHtml(v.location_state || 'NA') + ' ' + escapeHtml(v.location_zip || '') + '</p>',
            '    <p>Engine: ' + escapeHtml(v.engine_type || v.fuel_type || 'N/A') + ' | Transmission: ' + escapeHtml(v.transmission || 'N/A') + ' | Ext/Int: ' + escapeHtml(v.exterior_color || 'N/A') + ' / ' + escapeHtml(v.interior_color || 'N/A') + '</p>',
            '    <p>Days on Market: ' + escapeHtml(String(v.days_on_market || 'N/A')) + ' | Dealer: ' + escapeHtml(v.dealer_name || 'N/A') + '</p>',
            description,
            '    <div class="vinv-feature-wrap">' + (features || '<span class="vinv-feature">No listed features</span>') + '</div>',
            '    <div class="vinv-actions">',
            '      <button class="vinv-btn" data-modal-action="garage" data-vin="' + escapeAttr(v.vin) + '">Add to My Garage</button>',
            '      <button class="vinv-btn-ghost" data-modal-action="acquire" data-vin="' + escapeAttr(v.vin) + '">Start Acquisition</button>',
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
                loadInventory(1);
            });

            el.form.addEventListener('change', function (event) {
                var target = event.target;
                if (!target || !target.name) return;

                if (target.name === 'make') {
                    var modelSelect = el.form.querySelector('select[name="model"]');
                    var trimSelect = el.form.querySelector('select[name="trim"]');
                    if (modelSelect) modelSelect.value = '';
                    if (trimSelect) trimSelect.value = '';
                    loadFacets();
                    return;
                }

                if (target.name === 'model' || target.name === 'body_type' || target.name === 'state' || target.name === 'inventory_type') {
                    loadFacets();
                }
            });
        }

        if (el.resetBtn) {
            el.resetBtn.addEventListener('click', function () {
                if (!el.form) return;
                el.form.reset();

                var hasImages = el.form.querySelector('input[name="has_images"]');
                var liveSync = el.form.querySelector('input[name="live_sync"]');
                var sortBy = el.form.querySelector('select[name="sort_by"]');
                var sortDir = el.form.querySelector('select[name="sort_dir"]');

                if (hasImages) hasImages.checked = true;
                if (liveSync) liveSync.checked = true;
                if (sortBy) sortBy.value = 'updated_at';
                if (sortDir) sortDir.value = 'desc';

                loadFacets().then(function () {
                    loadInventory(1);
                });
            });
        }

        if (el.grid) {
            el.grid.addEventListener('click', async function (event) {
                var btn = event.target.closest('button');
                if (!btn) return;
                var action = btn.getAttribute('data-action');
                var vin = btn.getAttribute('data-vin');
                if (!action || !vin) return;

                if (action === 'detail') {
                    await openDetail(vin);
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
