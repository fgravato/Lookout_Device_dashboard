// Lookout MRA Dashboard JavaScript

class Dashboard {
    constructor() {
        this.devices = [];
        this.filteredDevices = [];
        this.deviceGroups = {};
        this.groupedView = false; // Toggle between individual and grouped view
        this.scrubEmail = false; // Toggle for email domain scrubbing
        this.activeStatsFilter = null; // Track active stats card filter
        this.lastVulnerabilitySearch = ''; // Track last vulnerability search to prevent duplicate searches
        this.tenants = []; // Multi-tenant support
        this.multiTenantEnabled = false; // Flag for multi-tenant mode
        this.init();
    }

    init() {
        this.currentSort = { field: null, direction: 'asc' };
        this.bindEvents();
        this.loadTenants(); // Load tenants first (if multi-tenant enabled)
        this.loadDevices();
    }

    bindEvents() {
        // Full refresh button
        document.getElementById('fullRefreshBtn').addEventListener('click', () => {
            this.performRefresh('full');
        });

        // Delta refresh button
        document.getElementById('deltaRefreshBtn').addEventListener('click', () => {
            this.performRefresh('delta');
        });

        // Clear cache button
        document.getElementById('clearCacheBtn').addEventListener('click', () => {
            this.clearCache();
        });

        // Search input
        document.getElementById('searchInput').addEventListener('input', () => {
            this.applyFilters();
        });

        // Vulnerability input - use Enter key or blur to trigger search
        const vulnerabilityInput = document.getElementById('vulnerabilityInput');
        vulnerabilityInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                this.applyFilters();
            }
        });
        vulnerabilityInput.addEventListener('blur', () => {
            // Only search on blur if the value has changed
            if (vulnerabilityInput.value.trim() !== this.lastVulnerabilitySearch) {
                this.applyFilters();
            }
        });

        // Platform filter
        document.getElementById('platformFilter').addEventListener('change', () => {
            this.applyFilters();
        });

        // Risk level filter
        document.getElementById('riskLevelFilter').addEventListener('change', () => {
            this.applyFilters();
        });

        // OS version filter
        document.getElementById('osVersionFilter').addEventListener('input', () => {
            this.applyFilters();
        });

        // Days filter
        document.getElementById('daysFilter').addEventListener('change', () => {
            this.applyFilters();
        });

        // Tenant filter
        document.getElementById('tenantFilter').addEventListener('change', () => {
            this.applyFilters();
        });

        // MDM Provider filter
        document.getElementById('mdmProviderFilter').addEventListener('change', () => {
            this.applyFilters();
        });

        // Group view toggle
        document.getElementById('groupViewToggle').addEventListener('change', (e) => {
            this.groupedView = e.target.checked;
            if (this.groupedView) {
                this.loadDeviceGroups();
            } else {
                this.renderDevices();
            }
        });

        // Scrub email toggle
        document.getElementById('scrubEmailToggle').addEventListener('change', (e) => {
            this.scrubEmail = e.target.checked;
            this.renderDevices();
        });

        // Clear filters
        document.getElementById('clearFilters').addEventListener('click', () => {
            this.clearFilters();
        });

        // Export button
        document.getElementById('exportBtn').addEventListener('click', () => {
            this.showExportModal();
        });

        // Export modal confirm button
        document.getElementById('confirmExportBtn').addEventListener('click', () => {
            this.performExport();
        });

        // Sortable column headers
        document.querySelectorAll('.sortable').forEach(header => {
            header.addEventListener('click', () => {
                const sortField = header.getAttribute('data-sort');
                this.sortDevices(sortField);
            });
        });

        // Stats card click handlers
        document.querySelectorAll('.stats-card').forEach(card => {
            card.addEventListener('click', () => {
                const filterType = card.getAttribute('data-filter');
                this.filterByStatsCard(filterType);
            });

            // Add keyboard support
            card.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    const filterType = card.getAttribute('data-filter');
                    this.filterByStatsCard(filterType);
                }
            });
        });
    }

    async loadDevices(forceRefresh = false) {
        this.showLoading(true);

        try {
            const url = forceRefresh ? '/api/devices?force_refresh=true' : '/api/devices';
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            this.devices = data.devices || [];
            this.filteredDevices = [...this.devices];

            // Check if any device has MDM connector data
            const hasMdmData = this.devices.some(d => d.mdm_connector_id || d.tenant_name || d.mdm_provider);
            if (hasMdmData) {
                // Show MDM column
                const mdmColumn = document.getElementById('mdmColumnHeader');
                if (mdmColumn) {
                    mdmColumn.style.display = 'table-cell';
                }

                // Show MDM filter dropdowns and populate them
                this.showMdmFilters();
            }

            this.updateStats();
            this.renderDevices();

            // Update cache info display
            this.updateCacheInfo(data.cache_info);

        } catch (error) {
            console.error('Error loading devices:', error);
            this.showError('Failed to load device data. Please try again.');
        } finally {
            this.showLoading(false);
        }
    }

    async loadDevicesByVulnerability(cveName) {
        this.showLoading(true);

        try {
            const url = `/api/vulnerabilities/${encodeURIComponent(cveName)}`;
            const response = await fetch(url);
            if (!response.ok) {
                if (response.status === 404) {
                    throw new Error(`No devices found affected by ${cveName}`);
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            this.filteredDevices = data.devices || [];

            // Update stats for vulnerability view
            this.updateStats();

            // Show vulnerability info in header
            this.showVulnerabilityInfo(cveName, data.device_count);

            this.renderDevices();

        } catch (error) {
            console.error('Error loading vulnerability devices:', error);
            this.showError(`Failed to load devices for ${cveName}: ${error.message}`);
            // Clear vulnerability filter on error
            document.getElementById('vulnerabilityInput').value = '';
            this.applyFilters();
        } finally {
            this.showLoading(false);
        }
    }

    showVulnerabilityInfo(cveName, deviceCount) {
        // Update page title or add a banner showing vulnerability info
        const headerElement = document.querySelector('.navbar-brand');
        const originalText = 'Lookout MRA Device Dashboard';

        if (!headerElement) return;

        if (deviceCount > 0) {
            headerElement.innerHTML = `
                <i class="fas fa-shield-alt me-2"></i>
                ${originalText}
                <span class="badge bg-warning text-dark ms-2">
                    <i class="fas fa-exclamation-triangle me-1"></i>
                    ${cveName}: ${deviceCount} affected devices
                </span>
            `;
        } else {
            headerElement.innerHTML = `
                <i class="fas fa-shield-alt me-2"></i>
                ${originalText}
            `;
        }
    }

    async loadDeviceGroups() {
        this.showLoading(true);

        try {
            // Get current filter selections
            const connectionFilter = document.getElementById('daysFilter').value;
            const riskLevelFilter = document.getElementById('riskLevelFilter').value;
            const platformFilter = document.getElementById('platformFilter').value;

            // Build query parameters
            const params = new URLSearchParams();
            if (connectionFilter) params.append('connection_filter', connectionFilter);
            if (riskLevelFilter) params.append('risk_level', riskLevelFilter);
            if (platformFilter) params.append('platform', platformFilter);

            const url = `/api/devices/groups?${params.toString()}`;

            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            this.deviceGroups = data.groups || {};
            this.renderDeviceGroups();

        } catch (error) {
            console.error('Error loading device groups:', error);
            this.showError('Failed to load device groups. Please try again.');
        } finally {
            this.showLoading(false);
        }
    }

    async performRefresh(type = 'full') {
        this.showLoading(true);

        try {
            const response = await fetch(`/api/refresh?type=${type}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            console.log('Refresh result:', result);

            // Reload devices after refresh
            await this.loadDevices();

            // Clear vulnerability filter after refresh
            document.getElementById('vulnerabilityInput').value = '';
            this.showVulnerabilityInfo('', 0);

            // Show success message
            this.showSuccess(`${result.message} (${result.devices_updated} devices updated)`);

        } catch (error) {
            console.error('Error during refresh:', error);
            this.showError('Failed to refresh device data. Please try again.');
        } finally {
            this.showLoading(false);
        }
    }

    async clearCache() {
        try {
            const response = await fetch('/api/cache/clear');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            console.log('Cache clear result:', result);

            // Reload devices after clearing cache
            await this.loadDevices(true);

            this.showSuccess('Cache cleared successfully');

        } catch (error) {
            console.error('Error clearing cache:', error);
            this.showError('Failed to clear cache. Please try again.');
        }
    }

    updateCacheInfo(cacheInfo) {
        if (!cacheInfo) return;

        // Update last update time
        const lastUpdateElement = document.getElementById('lastUpdateTime');
        if (cacheInfo.last_updated) {
            const lastUpdate = new Date(cacheInfo.last_updated);
            lastUpdateElement.textContent = lastUpdate.toLocaleString();
        } else {
            lastUpdateElement.textContent = 'Never';
        }

        // Update cache age
        const cacheAgeElement = document.getElementById('cacheAge');
        if (cacheInfo.cache_age_minutes !== null && cacheInfo.cache_age_minutes !== undefined) {
            const minutes = Math.round(cacheInfo.cache_age_minutes);
            cacheAgeElement.textContent = `${minutes} minutes`;
            cacheAgeElement.className = minutes > 60 ? 'text-warning' : 'text-success';
        } else {
            cacheAgeElement.textContent = 'Unknown';
            cacheAgeElement.className = '';
        }

        // Update API response time
        const apiTimeElement = document.getElementById('apiResponseTime');
        if (cacheInfo.api_response_time) {
            const seconds = cacheInfo.api_response_time.toFixed(2);
            apiTimeElement.textContent = `${seconds}s`;
            apiTimeElement.className = cacheInfo.api_response_time > 5 ? 'text-warning' : 'text-success';
        } else {
            apiTimeElement.textContent = 'Unknown';
            apiTimeElement.className = '';
        }
    }

    applyFilters() {
        const searchTerm = document.getElementById('searchInput').value.toLowerCase();
        const platformFilter = document.getElementById('platformFilter').value;
        const riskLevelFilter = document.getElementById('riskLevelFilter').value;
        const osVersionFilter = document.getElementById('osVersionFilter').value.trim();
        const daysFilter = document.getElementById('daysFilter').value;
        const vulnerabilityFilter = document.getElementById('vulnerabilityInput').value.trim();
        const tenantFilter = document.getElementById('tenantFilter').value;
        const mdmProviderFilter = document.getElementById('mdmProviderFilter').value;

        // If vulnerability filter is active, fetch devices for that CVE instead
        if (vulnerabilityFilter) {
            // Update last search term to prevent duplicate searches
            this.lastVulnerabilitySearch = vulnerabilityFilter;
            this.loadDevicesByVulnerability(vulnerabilityFilter);
            return;
        } else {
            // Clear last search term when vulnerability filter is cleared
            this.lastVulnerabilitySearch = '';
        }

        this.filteredDevices = this.devices.filter(device => {
            // Search filter
            if (searchTerm && !device.device_name.toLowerCase().includes(searchTerm) &&
                !device.user_email.toLowerCase().includes(searchTerm)) {
                return false;
            }

            // Platform filter
            if (platformFilter && device.platform.toLowerCase() !== platformFilter) {
                return false;
            }

            // Risk level filter (from dropdown)
            if (riskLevelFilter && device.risk_level.toLowerCase() !== riskLevelFilter) {
                return false;
            }

            // OS version filter
            if (osVersionFilter) {
                const deviceOsVersion = (device.os_version || '').toLowerCase();
                if (!deviceOsVersion.includes(osVersionFilter.toLowerCase())) {
                    return false;
                }
            }

            // Tenant filter (multi-tenant mode or connector mode)
            if (tenantFilter) {
                // Support filtering by tenant_id, mdm_identifier, OR mdm_connector_id
                // Convert comparison values to string to handle numeric connector IDs
                const matchTenant = device.tenant_id && String(device.tenant_id) === tenantFilter;
                const matchMdmId = device.mdm_identifier && String(device.mdm_identifier) === tenantFilter;
                const matchConnector = device.mdm_connector_id && String(device.mdm_connector_id) === tenantFilter;

                if (!matchTenant && !matchMdmId && !matchConnector) {
                    return false;
                }
            }

            // MDM Provider filter
            if (mdmProviderFilter) {
                const normalizedType = this.normalizeMdmType(device.mdm_type);
                const providerMatch = normalizedType === mdmProviderFilter;
                const explicitMatch = device.mdm_provider === mdmProviderFilter;

                if (!providerMatch && !explicitMatch) {
                    return false;
                }
            }

            // Stats card filter (overrides dropdown risk filter)
            if (this.activeStatsFilter && this.activeStatsFilter !== 'all') {
                if (!this.matchesStatsFilter(device, this.activeStatsFilter)) {
                    return false;
                }
            }

            // Connection status filter (using new preset logic)
            if (daysFilter) {
                const daysSince = device.days_since_checkin;

                if (!this.matchesConnectionFilter(daysSince, daysFilter)) {
                    return false;
                }
            }

            return true;
        });

        this.updateStats();

        if (this.groupedView) {
            this.loadDeviceGroups();
        } else {
            this.renderDevices();
        }

        // Maintain current sort after filtering
        if (this.currentSort.field && !this.groupedView) {
            this.sortDevices(this.currentSort.field);
        }
    }

    filterByStatsCard(filterType) {
        // Update active filter
        this.activeStatsFilter = filterType;

        // Update visual state of cards
        this.updateStatsCardVisualState(filterType);

        // Clear the risk level dropdown if stats filter is active
        if (filterType !== 'all') {
            document.getElementById('riskLevelFilter').value = '';
        }

        // Apply filters
        this.applyFilters();
    }

    matchesStatsFilter(device, filterType) {
        const riskLevel = device.risk_level.toLowerCase();

        switch (filterType) {
            case 'low':
                return riskLevel === 'secure' || riskLevel === 'low';
            case 'medium':
                return riskLevel === 'medium';
            case 'high':
                return riskLevel === 'high' || riskLevel === 'critical';
            case 'all':
            default:
                return true;
        }
    }

    matchesConnectionFilter(daysSince, filterPreset) {
        if (daysSince === null || daysSince < 0) {
            return filterPreset === 'never_connected';
        }

        switch (filterPreset) {
            case 'connected':
                return daysSince <= 1;
            case 'recent':
                return daysSince >= 2 && daysSince <= 7;
            case 'stale':
                return daysSince >= 8 && daysSince <= 30;
            case 'disconnected':
                return daysSince >= 31 && daysSince <= 90;
            case 'very_stale':
                return daysSince > 90;
            default:
                return true;
        }
    }

    getConnectionStatusInfo(daysSince) {
        if (daysSince === null || daysSince < 0) {
            return {
                status: 'never_connected',
                label: 'Never Connected',
                color: '#6c757d',
                severity: 'secondary',
                icon: 'question-circle'
            };
        } else if (daysSince <= 1) {
            return {
                status: 'connected',
                label: 'Connected',
                color: '#28a745',
                severity: 'success',
                icon: 'check-circle'
            };
        } else if (daysSince <= 7) {
            return {
                status: 'recent',
                label: 'Recent',
                color: '#17a2b8',
                severity: 'info',
                icon: 'info-circle'
            };
        } else if (daysSince <= 30) {
            return {
                status: 'stale',
                label: 'Stale',
                color: '#ffc107',
                severity: 'warning',
                icon: 'exclamation-triangle'
            };
        } else if (daysSince <= 90) {
            return {
                status: 'disconnected',
                label: 'Disconnected',
                color: '#fd7e14',
                severity: 'warning',
                icon: 'exclamation-triangle'
            };
        } else {
            return {
                status: 'very_stale',
                label: 'Very Stale',
                color: '#dc3545',
                severity: 'danger',
                icon: 'times-circle'
            };
        }
    }

    updateStatsCardVisualState(activeFilter) {
        document.querySelectorAll('.stats-card').forEach(card => {
            const filterType = card.getAttribute('data-filter');
            if (filterType === activeFilter) {
                card.classList.add('active');
            } else {
                card.classList.remove('active');
            }
        });
    }

    clearFilters() {
        document.getElementById('searchInput').value = '';
        document.getElementById('platformFilter').value = '';
        document.getElementById('riskLevelFilter').value = '';
        document.getElementById('osVersionFilter').value = '';
        document.getElementById('daysFilter').value = '';
        document.getElementById('vulnerabilityInput').value = '';
        document.getElementById('tenantFilter').value = '';
        document.getElementById('mdmProviderFilter').value = '';

        // Clear vulnerability search tracking
        this.lastVulnerabilitySearch = '';

        // Clear stats card filter
        this.activeStatsFilter = null;
        this.updateStatsCardVisualState('all');

        this.filteredDevices = [...this.devices];
        this.updateStats();

        if (this.groupedView) {
            this.loadDeviceGroups();
        } else {
            this.renderDevices();
        }

        // Maintain current sort after clearing filters
        if (this.currentSort.field && !this.groupedView) {
            this.sortDevices(this.currentSort.field);
        }
    }

    sortDevices(field) {
        // Toggle sort direction if clicking the same field
        if (this.currentSort.field === field) {
            this.currentSort.direction = this.currentSort.direction === 'asc' ? 'desc' : 'asc';
        } else {
            this.currentSort.field = field;
            this.currentSort.direction = 'asc';
        }

        // Sort the filtered devices
        this.filteredDevices.sort((a, b) => {
            let aVal = a[field];
            let bVal = b[field];

            // Handle different data types
            if (field === 'days_since_checkin' || field === 'active_issues_count') {
                aVal = parseInt(aVal) || 0;
                bVal = parseInt(bVal) || 0;
            } else if (field === 'last_checkin') {
                aVal = new Date(aVal || 0);
                bVal = new Date(bVal || 0);
            } else if (field === 'risk_level') {
                // Custom sort order for risk levels
                const riskOrder = { 'secure': 1, 'low': 2, 'medium': 3, 'high': 4, 'critical': 5 };
                aVal = riskOrder[aVal.toLowerCase()] || 0;
                bVal = riskOrder[bVal.toLowerCase()] || 0;
            } else {
                // String comparison (case insensitive)
                aVal = (aVal || '').toString().toLowerCase();
                bVal = (bVal || '').toString().toLowerCase();
            }

            let result = 0;
            if (aVal < bVal) result = -1;
            else if (aVal > bVal) result = 1;

            return this.currentSort.direction === 'desc' ? -result : result;
        });

        // Update sort indicators
        this.updateSortIndicators();

        // Re-render the table
        this.renderDevices();
    }

    updateSortIndicators() {
        // Reset all sort icons
        document.querySelectorAll('.sort-icon').forEach(icon => {
            icon.className = 'fas fa-sort sort-icon';
        });

        // Update the active sort icon
        if (this.currentSort.field) {
            const activeHeader = document.querySelector(`[data-sort="${this.currentSort.field}"] .sort-icon`);
            if (activeHeader) {
                activeHeader.className = `fas fa-sort-${this.currentSort.direction === 'asc' ? 'up' : 'down'} sort-icon active`;
            }
        }
    }

    updateStats() {
        const total = this.filteredDevices.length;
        const lowRisk = this.filteredDevices.filter(d =>
            d.risk_level.toLowerCase() === 'secure' || d.risk_level.toLowerCase() === 'low'
        ).length;
        const mediumRisk = this.filteredDevices.filter(d => d.risk_level.toLowerCase() === 'medium').length;
        const highRisk = this.filteredDevices.filter(d =>
            d.risk_level.toLowerCase() === 'high' || d.risk_level.toLowerCase() === 'critical'
        ).length;

        document.getElementById('totalDevices').textContent = total;
        document.getElementById('lowRisk').textContent = lowRisk;
        document.getElementById('mediumRisk').textContent = mediumRisk;
        document.getElementById('highRisk').textContent = highRisk;
    }

    renderDevices() {
        if (this.groupedView) {
            this.renderDeviceGroups();
            return;
        }

        const tbody = document.getElementById('devicesTableBody');
        const hasMdmColumn = this.multiTenantEnabled || (this.devices && this.devices.some(d => d.mdm_connector_id || d.mdm_type));
        const colspan = hasMdmColumn ? "11" : "10";

        if (this.filteredDevices.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="${colspan}" class="text-center">
                        <div class="empty-state">
                            <i class="fas fa-search"></i>
                            <p>No devices found matching your criteria.</p>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = this.filteredDevices.map(device => {
            const daysSince = device.days_since_checkin !== undefined ? device.days_since_checkin : this.calculateDaysSince(device.last_checkin);
            const riskClass = `risk-${device.risk_level.toLowerCase()}`;
            const complianceIcon = this.getComplianceIcon(device.compliance_status);
            const activeIssues = device.active_issues_count || 0;
            const issuesClass = activeIssues > 0 ? (activeIssues >= 3 ? 'text-danger fw-bold' : 'text-warning fw-bold') : 'text-success';

            // Get connection status info
            const connectionInfo = device.connection_status_info || this.getConnectionStatusInfo(daysSince);
            const connectionStatusHtml = `
                <span class="badge bg-${connectionInfo.severity}" style="color: white;">
                    <i class="fas fa-${connectionInfo.icon} me-1"></i>
                    ${connectionInfo.label}
                </span>
            `;

            return `
                <tr class="fade-in device-row" data-device-id="${device.device_id}" title="Click to view device details">
                    <td>
                        <strong>${this.escapeHtml(device.device_name)}</strong>
                        ${device.manufacturer ? `<br><small class="text-muted">${this.escapeHtml(device.manufacturer)} ${this.escapeHtml(device.model || '')}</small>` : ''}
                    </td>
                    <td>${this.escapeHtml(this.scrubEmailDomain(device.user_email))}</td>
                    <td>
                        <i class="fab fa-${this.getPlatformIcon(device.platform)} me-1"></i>
                        ${this.escapeHtml(device.platform)}
                    </td>
                    <td>
                        <span class="${riskClass}">${this.escapeHtml(device.risk_level)}</span>
                    </td>
                    <td>
                        <span class="${issuesClass}">${activeIssues}</span>
                    </td>
                    <td>${device.last_checkin !== 'Never' ? this.formatDate(device.last_checkin) : 'Never'}</td>
                    <td>
                        ${daysSince >= 0 ? `${daysSince} days` : 'Never'}
                        <br>${connectionStatusHtml}
                    </td>
                    <td>${this.escapeHtml(device.os_version)}</td>
                    <td>
                        ${device.security_patch_level ? this.escapeHtml(device.security_patch_level) : 'N/A'}
                    </td>
                    <td>
                        <i class="${complianceIcon}"></i>
                        ${this.escapeHtml(device.compliance_status)}
                    </td>
                    ${hasMdmColumn ? `
                    <td>
                        <div class="d-flex flex-column">
                            ${device.tenant_name ? `<div class="mb-1"><i class="fas fa-building me-1 text-muted"></i><small class="fw-bold">${this.escapeHtml(device.tenant_name)}</small></div>` : ''}
                            
                            ${this.getMdmBrandBadge(device.mdm_type)}
                            
                            ${!device.mdm_type && device.mdm_provider ? `<div class="mb-1"><i class="fas fa-server me-1 text-muted"></i><small>${this.escapeHtml(device.mdm_provider)}</small></div>` : ''}
                            
                            ${device.mdm_connector_id ? `
                                <div class="text-muted" style="font-size: 0.75rem; line-height: 1.2;">
                                    <span class="d-block">ID: ${this.escapeHtml(device.mdm_connector_id)}</span>
                                </div>
                            ` : ''}
                            ${device.external_id ? `
                                <div class="text-muted" style="font-size: 0.75rem; line-height: 1.2;">
                                    <span class="d-block text-truncate" style="max-width: 120px;" title="${this.escapeHtml(device.external_id)}">Ext: ${this.escapeHtml(device.external_id)}</span>
                                </div>
                            ` : ''}
                        </div>
                    </td>
                    ` : ''}
                </tr>
            `;
        }).join('');

        // Add click handlers to device rows after rendering
        this.addDeviceRowClickHandlers();
    }

    renderDeviceGroups() {
        const tbody = document.getElementById('devicesTableBody');
        const hasMdmColumn = this.multiTenantEnabled || (this.devices && this.devices.some(d => d.mdm_connector_id));
        const colspan = hasMdmColumn ? "11" : "10";

        if (Object.keys(this.deviceGroups).length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="${colspan}" class="text-center">
                        <div class="empty-state">
                            <i class="fas fa-search"></i>
                            <p>No device groups found matching your current filters.</p>
                            <small class="text-muted">Try adjusting your filter criteria.</small>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = Object.entries(this.deviceGroups).map(([groupKey, groupData]) => {
            const severityClass = this.getSeverityClass(groupData.severity);
            const deviceCount = groupData.devices.length;

            return `
                <tr class="group-row" data-group="${groupKey}">
                    <td colspan="${colspan}">
                        <div class="group-header ${severityClass}">
                            <div class="d-flex justify-content-between align-items-center">
                                <div style="cursor: pointer;" onclick="window.dashboard.toggleGroup('${groupKey}')">
                                    <i class="fas fa-chevron-right me-2 group-toggle-icon" id="icon-${groupKey}"></i>
                                    <strong>${this.escapeHtml(groupData.name)}</strong>
                                    <span class="badge bg-${severityClass} ms-2">${deviceCount} devices</span>
                                </div>
                                <div>
                                    <button class="btn btn-sm btn-outline-primary me-2" onclick="window.dashboard.exportGroup('${groupKey}', '${groupData.name}')">
                                        <i class="fas fa-file-excel me-1"></i>Export
                                    </button>
                                    <small class="text-muted">Severity: ${groupData.severity}</small>
                                </div>
                            </div>
                        </div>
                        <div class="group-devices" id="group-${groupKey}" style="display: none;">
                            ${groupData.devices.map(device => {
                const daysSince = device.days_since_checkin !== undefined ? device.days_since_checkin : this.calculateDaysSince(device.last_checkin);
                const riskClass = `risk-${device.risk_level.toLowerCase()}`;
                const complianceIcon = this.getComplianceIcon(device.compliance_status);
                const activeIssues = device.active_issues_count || 0;
                const issuesClass = activeIssues > 0 ? (activeIssues >= 3 ? 'text-danger fw-bold' : 'text-warning fw-bold') : 'text-success';

                const connectionInfo = device.connection_status_info || this.getConnectionStatusInfo(daysSince);
                const connectionStatusHtml = `
                                    <span class="badge bg-${connectionInfo.severity}" style="color: white;">
                                        <i class="fas fa-${connectionInfo.icon} me-1"></i>
                                        ${connectionInfo.label}
                                    </span>
                                `;

                const hasMdmData = this.multiTenantEnabled || device.mdm_connector_id;

                return `
                                    <div class="device-row ps-4 py-2 border-start border-${severityClass}" data-device-id="${device.device_id}" title="Click to view device details">
                                        <div class="row">
                                            <div class="col-md-2">
                                                <strong>${this.escapeHtml(device.device_name)}</strong>
                                                ${device.manufacturer ? `<br><small class="text-muted">${this.escapeHtml(device.manufacturer)} ${this.escapeHtml(device.model || '')}</small>` : ''}
                                            </div>
                                            <div class="col-md-2">${this.escapeHtml(this.scrubEmailDomain(device.user_email))}</div>
                                            <div class="col-md-1">
                                                <i class="fab fa-${this.getPlatformIcon(device.platform)} me-1"></i>
                                                ${this.escapeHtml(device.platform)}
                                            </div>
                                            <div class="col-md-1">
                                                <span class="${riskClass}">${this.escapeHtml(device.risk_level)}</span>
                                            </div>
                                            <div class="col-md-1">
                                                <span class="${issuesClass}">${activeIssues}</span>
                                            </div>
                                            <div class="col-md-1">${device.last_checkin !== 'Never' ? this.formatDate(device.last_checkin) : 'Never'}</div>
                                            <div class="col-md-1">
                                                ${daysSince >= 0 ? `${daysSince} days` : 'Never'}
                                                <br>${connectionStatusHtml}
                                            </div>
                                            <div class="col-md-1">${this.escapeHtml(device.os_version)}</div>
                                            <div class="col-md-1">
                                                ${device.security_patch_level ? this.escapeHtml(device.security_patch_level) : 'N/A'}
                                            </div>
                                            <div class="col-md-1">
                                                <i class="${complianceIcon}"></i>
                                                ${this.escapeHtml(device.compliance_status)}
                                            </div>
                                            ${hasMdmData ? `
                                            <div class="col-md-2">
                                                <small class="text-muted">
                                                    ${device.tenant_name ? `<i class="fas fa-building me-1"></i>${this.escapeHtml(device.tenant_name)}<br>` : ''}
                                                    ${device.mdm_provider ? `<i class="fas fa-server me-1"></i>${this.escapeHtml(device.mdm_provider)}<br>` : ''}
                                                    ${device.mdm_connector_id ? `<strong>MDM:</strong> ${this.escapeHtml(device.mdm_connector_id)}<br>` : ''}
                                                    ${device.external_id ? `<strong>Ext ID:</strong> ${this.escapeHtml(device.external_id)}` : ''}
                                                </small>
                                            </div>
                                            ` : ''}
                                        </div>
                                    </div>
                                `;
            }).join('')}
                        </div>
                    </td>
                </tr>
            `;
        }).join('');

        // Add click handlers to device rows in groups
        this.addDeviceRowClickHandlers();
    }

    addDeviceRowClickHandlers() {
        // Handle clicks on individual device rows (both in regular view and grouped view)
        document.querySelectorAll('.device-row[data-device-id]').forEach(row => {
            row.addEventListener('click', (e) => {
                const deviceId = row.getAttribute('data-device-id');
                this.showDeviceDetails(deviceId);
            });
        });
    }

    toggleGroup(groupKey) {
        console.log('Toggling group:', groupKey);
        const groupElement = document.getElementById(`group-${groupKey}`);
        const iconElement = document.getElementById(`icon-${groupKey}`);

        if (!groupElement) {
            console.error('Group element not found:', `group-${groupKey}`);
            return;
        }

        if (groupElement.style.display === 'none' || groupElement.style.display === '') {
            groupElement.style.display = 'block';
            if (iconElement) iconElement.className = 'fas fa-chevron-down me-2 group-toggle-icon';
            console.log('Group expanded');
        } else {
            groupElement.style.display = 'none';
            if (iconElement) iconElement.className = 'fas fa-chevron-right me-2 group-toggle-icon';
            console.log('Group collapsed');
        }
    }

    getSeverityClass(severity) {
        switch ((severity || '').toLowerCase()) {
            case 'low': return 'secondary';
            case 'medium': return 'warning';
            case 'high': return 'danger';
            case 'critical': return 'danger';
            default: return 'secondary';
        }
    }

    async exportGroup(groupKey, groupName) {
        try {
            // Get current filter selections
            const connectionFilter = document.getElementById('daysFilter').value;
            const riskLevelFilter = document.getElementById('riskLevelFilter').value;
            const platformFilter = document.getElementById('platformFilter').value;

            // Build query parameters for group export
            const params = new URLSearchParams();
            params.append('group', groupKey);
            if (connectionFilter) params.append('connection_filter', connectionFilter);
            if (riskLevelFilter) params.append('risk_level', riskLevelFilter);
            if (platformFilter) params.append('platform', platformFilter);

            console.log('Exporting group with params:', params.toString());

            // Trigger download
            const response = await fetch(`/api/export/excel?${params.toString()}`);
            console.log('Export response status:', response.status);

            if (!response.ok) {
                const errorText = await response.text();
                console.error('Export error response:', errorText);
                throw new Error(`Export failed: ${response.status} - ${errorText}`);
            }

            // Create download link
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;

            // Generate filename
            const timestamp = new Date().toISOString().split('T')[0];
            const sanitizedGroupName = groupName.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
            a.download = `lookout_devices_${sanitizedGroupName}_${timestamp}.xlsx`;

            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            this.showSuccess(`Exported ${groupName} group successfully`);

        } catch (error) {
            console.error('Export error:', error);
            this.showError(`Failed to export group: ${error.message}`);
        }
    }

    calculateDaysSince(dateString) {
        if (!dateString || dateString === 'Never' || dateString === 'N/A') {
            return -1;
        }

        try {
            const lastCheckin = new Date(dateString);
            if (isNaN(lastCheckin.getTime())) {
                return -1;
            }

            const now = new Date();
            const diffTime = Math.abs(now - lastCheckin);
            return Math.floor(diffTime / (1000 * 60 * 60 * 24));
        } catch (error) {
            return -1;
        }
    }

    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    getPlatformIcon(platform) {
        const icons = {
            'ios': 'apple',
            'android': 'android',
            'windows': 'windows',
            'macos': 'apple'
        };
        return icons[platform.toLowerCase()] || 'desktop';
    }

    getComplianceIcon(status) {
        switch (status.toLowerCase()) {
            case 'connected':
                return 'fas fa-check-circle text-success';
            case 'disconnected':
                return 'fas fa-times-circle text-danger';
            case 'pending':
                return 'fas fa-clock text-warning';
            default:
                return 'fas fa-question-circle text-muted';
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    scrubEmailDomain(email) {
        if (!email || !this.scrubEmail) return email;
        const atIndex = email.indexOf('@');
        if (atIndex === -1) return email;
        const username = email.substring(0, atIndex);
        return username + '@[DOMAIN]';
    }

    showExportModal() {
        const modal = new bootstrap.Modal(document.getElementById('exportModal'));
        modal.show();
    }

    async performExport() {
        const exportScope = document.querySelector('input[name="exportScope"]:checked').value;
        const exportFormat = document.querySelector('input[name="exportFormat"]:checked').value;

        // Close the modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('exportModal'));
        modal.hide();

        // Show loading
        this.showLoading(true);

        try {
            let url = `/api/export/${exportFormat}`;
            const params = new URLSearchParams();

            // Check if vulnerability filter is active
            const vulnerabilityFilter = document.getElementById('vulnerabilityInput').value.trim();
            if (vulnerabilityFilter) {
                // Export vulnerability-specific devices
                params.append('vulnerability', vulnerabilityFilter);
            } else if (exportScope === 'filtered') {
                // Add current filter parameters
                const searchTerm = document.getElementById('searchInput').value;
                const platformFilter = document.getElementById('platformFilter').value;
                const riskLevelFilter = document.getElementById('riskLevelFilter').value;
                const osVersionFilter = document.getElementById('osVersionFilter').value.trim();
                const daysFilter = document.getElementById('daysFilter').value;

                if (searchTerm) params.append('search', searchTerm);
                if (platformFilter) params.append('platform', platformFilter);
                if (riskLevelFilter) params.append('risk_level', riskLevelFilter);
                if (osVersionFilter) params.append('os_version', osVersionFilter);
                if (daysFilter) params.append('days_since_checkin', daysFilter);
            }
            // For 'all', no additional parameters needed

            if (params.toString()) {
                url += '?' + params.toString();
            }

            console.log('Exporting with URL:', url);

            const response = await fetch(url);
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Export failed: ${response.status} - ${errorText}`);
            }

            // Create download link
            const blob = await response.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = downloadUrl;

            // Generate filename
            const timestamp = new Date().toISOString().split('T')[0];
            let scopeText;
            if (vulnerabilityFilter) {
                scopeText = `vulnerability_${vulnerabilityFilter.replace(/-/g, '_').toLowerCase()}`;
            } else {
                scopeText = exportScope === 'all' ? 'all_devices' : 'filtered_devices';
            }
            const extension = exportFormat === 'excel' ? 'xlsx' : 'csv';
            a.download = `lookout_devices_${scopeText}_${timestamp}.${extension}`;

            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(downloadUrl);
            document.body.removeChild(a);

            const exportDescription = vulnerabilityFilter ?
                `${vulnerabilityFilter} affected devices` :
                (exportScope === 'all' ? 'all devices' : 'filtered devices');
            this.showSuccess(`Successfully exported ${exportDescription} as ${exportFormat.toUpperCase()}`);

        } catch (error) {
            console.error('Export error:', error);
            this.showError(`Failed to export data: ${error.message}`);
        } finally {
            this.showLoading(false);
        }
    }

    exportToExcel() {
        // Legacy method - kept for backward compatibility
        if (this.filteredDevices.length === 0) {
            this.showError('No data to export');
            return;
        }

        const csvContent = this.convertToCSV(this.filteredDevices);
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');

        if (link.download !== undefined) {
            const url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', `lookout-devices-${new Date().toISOString().split('T')[0]}.csv`);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
    }

    convertToCSV(data) {
        const headers = ['Device Name', 'User Email', 'Platform', 'Risk Level', 'Active Issues', 'Last Check-in', 'OS Version', 'Compliance Status'];
        const rows = data.map(device => [
            device.device_name,
            device.user_email,
            device.platform,
            device.risk_level,
            device.active_issues_count || 0,
            device.last_checkin,
            device.os_version,
            device.compliance_status
        ]);

        const csvRows = [headers, ...rows];
        return csvRows.map(row =>
            row.map(field => `"${String(field).replace(/"/g, '""')}"`).join(',')
        ).join('\n');
    }

    showLoading(show) {
        const spinner = document.getElementById('loadingSpinner');
        if (show) {
            spinner.classList.remove('d-none');
        } else {
            spinner.classList.add('d-none');
        }
    }

    showError(message) {
        const errorModal = new bootstrap.Modal(document.getElementById('errorModal'));
        document.getElementById('errorMessage').textContent = message;
        errorModal.show();
    }

    showSuccess(message) {
        // Create a simple toast notification
        const toast = document.createElement('div');
        toast.className = 'toast align-items-center text-white bg-success border-0 position-fixed top-0 end-0 m-3';
        toast.style.zIndex = '9999';
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas fa-check-circle me-2"></i>${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;

        document.body.appendChild(toast);
        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();

        // Remove toast after it's hidden
        toast.addEventListener('hidden.bs.toast', () => {
            document.body.removeChild(toast);
        });
    }

    // Device detail modal functionality
    showDeviceDetails(deviceId) {
        const modal = new bootstrap.Modal(document.getElementById('deviceDetailModal'));
        const content = document.getElementById('deviceDetailContent');

        // Show loading state
        content.innerHTML = `
            <div class="text-center">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2">Loading device details...</p>
            </div>
        `;

        modal.show();

        // Fetch device details
        fetch(`/api/device/${deviceId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to fetch device details');
                }
                return response.json();
            })
            .then(data => {
                this.renderDeviceDetails(data);
            })
            .catch(error => {
                console.error('Error fetching device details:', error);
                content.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        Failed to load device details. Please try again.
                    </div>
                `;
            });
    }

    renderDeviceDetails(deviceData) {
        const content = document.getElementById('deviceDetailContent');
        const device = deviceData.device || {};
        const riskAnalysis = deviceData.risk_analysis || {};

        const createDetailItem = (label, value, isMono = false) => `
            <div class="col-md-6 mb-3">
                <small class="text-secondary text-uppercase fw-bold" style="font-size: 0.7rem; letter-spacing: 0.5px; display: block; margin-bottom: 2px;">${label}</small>
                <div class="text-dark fw-medium ${isMono ? 'font-monospace' : ''} text-break">${value || '-'}</div>
            </div>
        `;

        const html = `
            <div class="container-fluid p-0">
                <!-- Basic Information -->
                <div class="card mb-3 border bg-light bg-opacity-10">
                    <div class="card-header bg-transparent border-bottom-0 pt-3 pb-1">
                        <h6 class="text-primary mb-0"><i class="fas fa-info-circle me-2"></i>Basic Information</h6>
                    </div>
                    <div class="card-body pt-2">
                        <div class="row">
                            ${createDetailItem('Device Name', device.device_name)}
                            ${createDetailItem('User Email', this.escapeHtml(this.scrubEmailDomain(device.user_email)))}
                            ${createDetailItem('Platform', `
                                <i class="fab fa-${this.getPlatformIcon(device.platform)} me-1 text-muted"></i>
                                ${device.platform}
                            `)}
                            ${createDetailItem('Manufacturer', device.manufacturer)}
                            ${createDetailItem('Model', device.model)}
                            ${createDetailItem('Activation Status', device.activation_status)}
                        </div>
                    </div>
                </div>

                <!-- MDM Information -->
                ${(device.mdm_connector_id || device.mdm_type || device.tenant_name) ? `
                <div class="card mb-3 border bg-light bg-opacity-10">
                    <div class="card-header bg-transparent border-bottom-0 pt-3 pb-1">
                        <h6 class="text-primary mb-0"><i class="fas fa-building me-2"></i>MDM / Tenant Information</h6>
                    </div>
                    <div class="card-body pt-2">
                        <div class="row">
                             ${device.tenant_name ? createDetailItem('Tenant', device.tenant_name) : ''}
                             
                             <div class="col-md-6 mb-3">
                                <small class="text-secondary text-uppercase fw-bold" style="font-size: 0.7rem; letter-spacing: 0.5px; display: block; margin-bottom: 2px;">MDM Provider</small>
                                <div>
                                    ${this.getMdmBrandBadge(device.mdm_type) || (device.mdm_provider ? device.mdm_provider : '-')}
                                </div>
                             </div>

                             ${createDetailItem('Connector ID', device.mdm_connector_id, true)}
                             ${createDetailItem('External ID', device.external_id, true)}
                        </div>
                    </div>
                </div>
                ` : ''}

                <!-- Security Status -->
                <div class="card mb-3 border bg-light bg-opacity-10">
                     <div class="card-header bg-transparent border-bottom-0 pt-3 pb-1">
                        <h6 class="text-primary mb-0"><i class="fas fa-shield-alt me-2"></i>Security Status</h6>
                    </div>
                    <div class="card-body pt-2">
                        <div class="row">
                            <div class="col-md-6 mb-3">
                                <small class="text-secondary text-uppercase fw-bold" style="font-size: 0.7rem; letter-spacing: 0.5px; display: block; margin-bottom: 2px;">Risk Level</small>
                                <div>
                                    <span class="badge ${this.getRiskBadgeClass(device.risk_level)} rounded-pill px-3">
                                        ${device.risk_level}
                                    </span>
                                </div>
                            </div>
                            ${createDetailItem('Security Status', device.security_status)}
                            ${createDetailItem('Protection Status', device.protection_status)}
                            <div class="col-md-6 mb-3">
                                <small class="text-secondary text-uppercase fw-bold" style="font-size: 0.7rem; letter-spacing: 0.5px; display: block; margin-bottom: 2px;">Compliance</small>
                                <div>
                                    <span class="badge ${this.getComplianceBadgeClass(device.compliance_status)} rounded-pill px-3">
                                        <i class="fas fa-check-circle me-1"></i>${device.compliance_status}
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="row">
                    <!-- Software Information -->
                    <div class="col-md-12">
                        <div class="card mb-3 border bg-light bg-opacity-10">
                            <div class="card-header bg-transparent border-bottom-0 pt-3 pb-1">
                                <h6 class="text-primary mb-0"><i class="fas fa-code me-2"></i>Software Information</h6>
                            </div>
                            <div class="card-body pt-2">
                                <div class="row">
                                    ${createDetailItem('OS Version', device.os_version)}
                                    ${createDetailItem('Latest OS Version', device.latest_os_version)}
                                    ${createDetailItem('Security Patch', device.security_patch_level)}
                                    ${createDetailItem('Latest Security Patch', device.latest_security_patch_level)}
                                    ${createDetailItem('App Version', device.app_version)}
                                    ${createDetailItem('SDK Version', device.sdk_version)}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                 <!-- Timing Information -->
                <div class="card mb-3 border bg-light bg-opacity-10">
                    <div class="card-header bg-transparent border-bottom-0 pt-3 pb-1">
                        <h6 class="text-primary mb-0"><i class="fas fa-clock me-2"></i>Timing Information</h6>
                    </div>
                    <div class="card-body pt-2">
                        <div class="row">
                             ${createDetailItem('Last Check-in', this.formatDateTime(device.last_checkin))}
                             ${createDetailItem('Days Since Check-in', device.days_since_checkin >= 0 ?
            `<span class="${device.days_since_checkin > 7 ? 'text-danger' : 'text-success'} fw-bold">${device.days_since_checkin} days</span>` : 'Unknown')}
                             ${createDetailItem('Activated At', this.formatDateTime(device.activated_at))}
                             ${createDetailItem('Last Updated', this.formatDateTime(device.updated_time))}
                        </div>
                    </div>
                </div>

                <!-- Risk Analysis -->
                <div class="card border-danger bg-danger bg-opacity-10 mt-4">
                    <div class="card-header bg-transparent border-bottom-0 pt-3">
                        <h6 class="text-danger mb-0"><i class="fas fa-exclamation-triangle me-2"></i>Risk Analysis</h6>
                    </div>
                    <div class="card-body">
                         <div class="d-flex align-items-center mb-3">
                            <strong class="me-2">Overall Risk Level:</strong>
                            <span class="badge ${this.getRiskBadgeClass(device.risk_level)} rounded-pill">
                                ${device.risk_level}
                            </span>
                        </div>
                        
                        <div class="alert alert-light border-0 shadow-sm">
                            <i class="fas fa-info-circle text-info me-2"></i>
                            <strong>Explanation:</strong> ${riskAnalysis.risk_explanation}
                        </div>
                        
                        ${riskAnalysis.risk_factors && riskAnalysis.risk_factors.length > 0 ? `
                            <h6 class="mt-4 mb-3 ps-1 border-start border-4 border-danger">&nbsp;Contributing Risk Factors <span class="badge bg-secondary rounded-pill ms-2">${riskAnalysis.total_issues}</span></h6>
                            <div class="list-group list-group-flush bg-transparent">
                            ${riskAnalysis.risk_factors.map(factor => `
                                <div class="list-group-item bg-transparent px-3 py-3 border-bottom border-light">
                                    <div class="d-flex w-100 justify-content-between align-items-center mb-1">
                                        <h6 class="mb-0 fw-bold text-dark">${factor.issue}</h6>
                                        <span class="badge ${this.getSeverityBadgeClass(factor.severity)}">${factor.severity}</span>
                                    </div>
                                    <p class="mb-1 text-muted small">${factor.description}</p>
                                    <small class="text-danger fw-bold"><i class="fas fa-fire me-1"></i>Impact: ${factor.impact}</small>
                                </div>
                            `).join('')}
                            </div>
                        ` : `
                            <div class="text-center py-4 text-success">
                                <i class="fas fa-check-circle fa-2x mb-2"></i>
                                <p class="mb-0">No specific risk factors identified.</p>
                            </div>
                        `}
                        
                        ${deviceData.risk_analysis.recommendations.length > 0 ? `
                            <h6 class="mt-4 mb-3 ps-1 border-start border-4 border-success">&nbsp;Recommendations</h6>
                            <ul class="list-group list-group-flush rounded-3 shadow-sm">
                                ${deviceData.risk_analysis.recommendations.map(rec => `
                                    <li class="list-group-item">
                                        <i class="fas fa-arrow-right text-success me-2"></i>${rec}
                                    </li>`).join('')}
                            </ul>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;

        content.innerHTML = html;
    }

    getRiskBadgeClass(riskLevel) {
        const classes = {
            'Secure': 'bg-success',
            'Low': 'bg-info',
            'Medium': 'bg-warning',
            'High': 'bg-danger',
            'Critical': 'bg-danger'
        };
        return classes[riskLevel] || 'bg-secondary';
    }

    getComplianceBadgeClass(compliance) {
        const classes = {
            'Fully Compliant': 'bg-success',
            'Connected': 'bg-info',
            'At-Risk': 'bg-warning text-dark',
            'Disconnected': 'bg-danger',
            'Pending': 'bg-warning text-dark',
            'Pending Activation': 'bg-warning text-dark',
            'Non-Compliant': 'bg-danger',
            'Unknown': 'bg-secondary'
        };
        return classes[compliance] || 'bg-secondary';
    }

    getSeverityBadgeClass(severity) {
        const classes = {
            'Low': 'bg-success',
            'Medium': 'bg-warning text-dark',
            'High': 'bg-warning',
            'Critical': 'bg-danger'
        };
        return classes[severity] || 'bg-secondary';
    }

    getMdmBrandBadge(mdmType) {
        if (!mdmType) return '';

        const type = mdmType.toString().toLowerCase();
        let name = mdmType;
        let icon = 'server';
        let color = 'secondary';

        if (type.includes('intune') || type.includes('microsoft')) {
            name = 'Microsoft Intune';
            icon = 'windows'; // using windows icon for Microsoft
            color = 'primary';
        } else if (type.includes('workspace') || type.includes('airwatch')) {
            name = 'Workspace ONE';
            icon = 'layer-group';
            color = 'success';
        } else if (type.includes('mobileiron') || type.includes('ivanti')) {
            name = 'Ivanti / MobileIron';
            icon = 'cube';
            color = 'danger';
        } else if (type.includes('jamf')) {
            name = 'Jamf';
            icon = 'copyright';
            color = 'info';
        } else if (type.includes('maas360')) {
            name = 'MaaS360';
            icon = 'ibm'; // branding check needed, using logic
            color = 'primary bg-opacity-75';
        }

        return `
            <div class="mb-1">
                <span class="badge bg-${color}">
                    <i class="fas fa-${icon} me-1"></i>${this.escapeHtml(name)}
                </span>
            </div>
        `;
    }

    formatDateTime(dateString) {
        if (!dateString || dateString === 'Unknown') return 'Unknown';
        try {
            const date = new Date(dateString);
            return date.toLocaleString();
        } catch (e) {
            return dateString;
        }
    }

    // Add click handlers to device rows
    addDeviceRowClickHandlers() {
        document.querySelectorAll('.device-row[data-device-id]').forEach(row => {
            row.addEventListener('click', (e) => {
                // Don't trigger if clicking on a button or link
                if (e.target.tagName === 'BUTTON' || e.target.tagName === 'A' || e.target.closest('button') || e.target.closest('a')) {
                    return;
                }

                const deviceId = row.getAttribute('data-device-id');
                if (deviceId) {
                    this.showDeviceDetails(deviceId);
                }
            });
        });
    }

    async loadTenants() {
        try {
            const response = await fetch('/api/tenants');

            // If endpoint returns 400, multi-tenant is not enabled
            if (response.status === 400) {
                this.multiTenantEnabled = false;
                return;
            }

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            this.tenants = data.tenants || [];
            this.multiTenantEnabled = this.tenants.length > 0;

            if (this.multiTenantEnabled) {
                this.populateTenantFilters(data);
                // Show tenant filter sections
                document.getElementById('tenantFilterGroup').style.display = 'block';
                document.getElementById('mdmProviderFilterGroup').style.display = 'block';
                // Show MDM column in table
                const mdmColumn = document.getElementById('mdmColumnHeader');
                if (mdmColumn) {
                    mdmColumn.style.display = 'table-cell';
                }
            }

        } catch (error) {
            console.log('Multi-tenant mode not enabled or error loading tenants:', error);
            this.multiTenantEnabled = false;
        }
    }

    populateTenantFilters(tenantsData) {
        const tenantSelect = document.getElementById('tenantFilter');
        const mdmProviderSelect = document.getElementById('mdmProviderFilter');

        // Clear existing options (except first "All" option)
        tenantSelect.innerHTML = '<option value="">All Tenants</option>';
        mdmProviderSelect.innerHTML = '<option value="">All MDM Providers</option>';

        // Populate tenant dropdown
        if (tenantsData.tenants) {
            tenantsData.tenants.forEach(tenant => {
                const option = document.createElement('option');
                option.value = tenant.tenant_id;
                option.textContent = `${tenant.tenant_name} (${tenant.mdm_identifier})`;
                tenantSelect.appendChild(option);
            });
        }

        // Populate MDM provider dropdown (unique providers)
        if (tenantsData.mdm_providers) {
            tenantsData.mdm_providers.forEach(provider => {
                const option = document.createElement('option');
                option.value = provider;
                option.textContent = provider;
                mdmProviderSelect.appendChild(option);
            });
        }

        // Update hint text with tenant count
        const hintElement = document.getElementById('tenantFilterHint');
        if (hintElement && tenantsData.enabled_tenants) {
            hintElement.textContent = `Filter devices by tenant or MDM (${tenantsData.enabled_tenants} tenants configured)`;
        }
    }

    normalizeMdmType(type) {
        if (!type) return null;
        const lower = type.toString().toLowerCase();
        if (lower.includes('intune') || lower.includes('microsoft')) return 'Microsoft Intune';
        if (lower.includes('workspace') || lower.includes('airwatch')) return 'Workspace ONE';
        if (lower.includes('mobileiron') || lower.includes('ivanti')) return 'Ivanti / MobileIron';
        if (lower.includes('jamf')) return 'Jamf';
        if (lower.includes('maas360')) return 'MaaS360';
        return type;
    }

    showMdmFilters() {
        // Extract unique MDM data from loaded devices
        const uniqueTenants = new Set();
        const uniqueMdmProviders = new Set();
        const uniqueMdmConnectors = new Set();

        this.devices.forEach(device => {
            if (device.tenant_name) {
                uniqueTenants.add(JSON.stringify({
                    id: device.tenant_id,
                    name: device.tenant_name,
                    mdm: device.mdm_identifier
                }));
            }

            // Collect MDM Providers (prefer normalized type, fallback to explicit provider name)
            const normalizedType = this.normalizeMdmType(device.mdm_type);
            if (normalizedType) uniqueMdmProviders.add(normalizedType);
            else if (device.mdm_provider) uniqueMdmProviders.add(device.mdm_provider);

            // Collect Connectors
            if (device.mdm_connector_id) uniqueMdmConnectors.add(device.mdm_connector_id);
        });

        const tenantSelect = document.getElementById('tenantFilter');
        const mdmProviderSelect = document.getElementById('mdmProviderFilter');

        // Populate Tenant/Connector Dropdown
        // If we have real tenants, use those. If not, but we have multiple connectors, use those.
        tenantSelect.innerHTML = '<option value="">All Tenants / Connectors</option>';

        if (uniqueTenants.size > 0) {
            uniqueTenants.forEach(tenantJson => {
                const tenant = JSON.parse(tenantJson);
                const option = document.createElement('option');
                option.value = tenant.id || tenant.name;
                option.textContent = tenant.mdm ? `${tenant.name} (${tenant.mdm})` : tenant.name;
                tenantSelect.appendChild(option);
            });
            document.getElementById('tenantFilterGroup').style.display = 'block';
        } else if (uniqueMdmConnectors.size > 0) {
            // Fallback: Populate with Connectors if no explicit Tenants
            uniqueMdmConnectors.forEach(connectorId => {
                const option = document.createElement('option');
                option.value = connectorId;
                option.textContent = `Connector: ${connectorId}`;
                tenantSelect.appendChild(option);
            });
            // Show the filter, label it appropriately if possible (UI label changes might reset, but content is key)
            document.getElementById('tenantFilterGroup').style.display = 'block';
        }

        // Populate MDM Provider dropdown
        mdmProviderSelect.innerHTML = '<option value="">All MDM Providers</option>';
        Array.from(uniqueMdmProviders).sort().forEach(provider => {
            const option = document.createElement('option');
            option.value = provider;
            option.textContent = provider;
            mdmProviderSelect.appendChild(option);
        });

        if (uniqueMdmProviders.size > 0) {
            document.getElementById('mdmProviderFilterGroup').style.display = 'block';
        }

        // Update hint
        const hintElement = document.getElementById('tenantFilterHint');
        if (hintElement) {
            const tenantCount = uniqueTenants.size > 0 ? uniqueTenants.size : uniqueMdmConnectors.size;
            const typeLabel = uniqueTenants.size > 0 ? 'tenant(s)' : 'connector(s)';
            const providerCount = uniqueMdmProviders.size;
            hintElement.textContent = `${tenantCount} ${typeLabel}, ${providerCount} MDM provider(s)`;
        }
    }
}

// CVE Scanner functionality
class CVEScanner {
    constructor() {
        this.lastScanResults = null;
        this.initEventListeners();
    }

    initEventListeners() {
        const scanBtn = document.getElementById('startCveScanBtn');
        const exportBtn = document.getElementById('exportCveReportBtn');
        const exportCveDevicesBtn = document.getElementById('exportCveDevicesBtn');

        if (scanBtn) {
            scanBtn.addEventListener('click', () => this.startScan());
        }

        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.exportReport());
        }

        if (exportCveDevicesBtn) {
            exportCveDevicesBtn.addEventListener('click', () => this.exportCveDevices());
        }
    }

    async startScan() {
        const severityFilter = document.getElementById('cveSeverityFilter').value;
        const activityFilter = document.getElementById('cveActivityFilter').value;

        // Check if device data is loaded
        const cacheStats = await this.checkCacheStatus();
        if (!cacheStats.hasDevices) {
            const proceed = confirm(
                'No device data loaded yet. CVE scan results may be incomplete.\n\n' +
                'Would you like to load devices first? (Recommended)\n\n' +
                'Click OK to load devices, or Cancel to scan anyway.'
            );

            if (proceed) {
                // Switch to Devices tab and load data
                const devicesTab = document.querySelector('[data-bs-target="#devices"]');
                if (devicesTab) {
                    devicesTab.click();
                    // Give user time to see the devices loading
                    alert('Please wait for devices to load, then return to CVE Scanner tab and scan again.');
                    return;
                }
            }
        }

        // Show scanning indicator
        document.getElementById('cvePlaceholder').style.display = 'none';
        document.getElementById('cveScanningIndicator').style.display = 'block';
        document.getElementById('cveSummaryCards').style.display = 'none';
        document.getElementById('cveSeverityCard').style.display = 'none';
        document.getElementById('cveTopCvesCard').style.display = 'none';
        document.getElementById('startCveScanBtn').disabled = true;

        try {
            const url = `/api/cve/scan?min_severity=${severityFilter}&max_days_since_checkin=${activityFilter}`;
            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`Scan failed: ${response.statusText}`);
            }

            const data = await response.json();
            this.lastScanResults = data;
            this.displayResults(data);

        } catch (error) {
            console.error('CVE scan error:', error);
            this.showError('CVE Scan Failed', error.message);
            document.getElementById('cveScanningIndicator').style.display = 'none';
            document.getElementById('cvePlaceholder').style.display = 'block';
        } finally {
            document.getElementById('startCveScanBtn').disabled = false;
        }
    }

    displayResults(data) {
        const summary = data.summary || {};
        const topCves = data.top_cves || [];
        const severityBreakdown = summary.severity_breakdown || {};

        // Store full vulnerability data for later use
        this.allVulnerabilities = data.all_vulnerabilities || [];

        // Hide scanning indicator
        document.getElementById('cveScanningIndicator').style.display = 'none';

        // Show summary cards
        document.getElementById('cveSummaryCards').style.display = 'flex';

        // Show scan info with filter details
        const filterMeta = data.filter_metadata || {};
        const devicesScanned = summary.total_devices || 0;
        const excludedDevices = filterMeta.excluded_stale_devices || 0;

        let scannedText = devicesScanned.toString();
        if (excludedDevices > 0) {
            scannedText += ` <small class="text-muted">(${excludedDevices} stale excluded)</small>`;
        }
        document.getElementById('cveDevicesScanned').innerHTML = scannedText;

        document.getElementById('cveDevicesAffected').textContent = summary.devices_with_vulnerabilities || 0;
        document.getElementById('cveTotalCves').textContent = summary.total_cves_found || 0;
        document.getElementById('cveVulnPercentage').textContent =
            `${(summary.vulnerability_percentage || 0).toFixed(1)}%`;

        // Show severity breakdown
        document.getElementById('cveSeverityCard').style.display = 'block';
        document.getElementById('cveCriticalCount').textContent = severityBreakdown.Critical || 0;
        document.getElementById('cveHighCount').textContent = severityBreakdown.High || 0;
        document.getElementById('cveMediumCount').textContent = severityBreakdown.Medium || 0;
        document.getElementById('cveLowCount').textContent = severityBreakdown.Low || 0;

        // Show top CVEs
        if (topCves.length > 0) {
            document.getElementById('cveTopCvesCard').style.display = 'block';
            const tbody = document.getElementById('cveTopCvesBody');
            tbody.innerHTML = topCves.slice(0, 10).map((cve, index) => `
                <tr class="cve-row" data-cve="${cve.cve}" style="cursor: pointer;">
                    <td><strong>${index + 1}</strong></td>
                    <td><code class="text-primary">${cve.cve}</code></td>
                    <td><span class="badge bg-danger">${cve.affected_devices}</span></td>
                </tr>
            `).join('');

            // Add click listeners to CVE rows
            document.querySelectorAll('.cve-row').forEach(row => {
                row.addEventListener('click', () => {
                    const cveName = row.getAttribute('data-cve');
                    this.showCveDetails(cveName);
                });
            });
        }

        // Enable export button
        document.getElementById('exportCveReportBtn').disabled = false;
    }

    async showCveDetails(cveName) {
        const modal = new bootstrap.Modal(document.getElementById('cveDetailsModal'));

        // Show loading state
        document.getElementById('cveDetailsLoading').style.display = 'block';
        document.getElementById('cveDetailsContent').style.display = 'none';
        document.getElementById('cveDetailsTitle').textContent = cveName;

        modal.show();

        try {
            // Get CVE details from API
            const response = await fetch(`/api/cve/${cveName}`);

            if (!response.ok) {
                throw new Error(`Failed to fetch CVE details: ${response.statusText}`);
            }

            const data = await response.json();
            this.displayCveDetails(cveName, data);

        } catch (error) {
            console.error('CVE details error:', error);
            document.getElementById('cveDetailsLoading').innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    Failed to load CVE details: ${error.message}
                </div>
            `;
        }
    }

    displayCveDetails(cveName, data) {
        // Find matching vulnerability from scan results
        const vuln = this.allVulnerabilities.find(v => v.cve === cveName) || {};

        // Hide loading, show content
        document.getElementById('cveDetailsLoading').style.display = 'none';
        document.getElementById('cveDetailsContent').style.display = 'block';

        // Populate CVE info
        document.getElementById('cveDetailId').textContent = cveName;
        document.getElementById('cveDetailDeviceCount').textContent = data.affected_devices_count || 0;
        document.getElementById('cveDetailPlatform').textContent = vuln.platform || 'Multiple';

        // Set external links
        document.getElementById('cveNvdLink').href = `https://nvd.nist.gov/vuln/detail/${cveName}`;
        document.getElementById('cveMitreLink').href = `https://cve.mitre.org/cgi-bin/cvename.cgi?name=${cveName}`;

        // Severity with color coding
        const severity = vuln.severity || 0;
        const severityLabel = vuln.severity_label || 'Unknown';
        let severityClass = 'secondary';
        if (severityLabel === 'Critical') severityClass = 'danger';
        else if (severityLabel === 'High') severityClass = 'warning';
        else if (severityLabel === 'Medium') severityClass = 'info';

        document.getElementById('cveDetailSeverity').innerHTML =
            `<span class="badge bg-${severityClass}">${severityLabel} (${severity.toFixed(1)})</span>`;

        document.getElementById('cveDetailDescription').textContent =
            vuln.description || data.cve_info?.description || 'No description available';

        // Populate affected devices table (deduplicated)
        const devices = data.affected_devices || [];
        const uniqueDevices = this.deduplicateDevices(devices);

        const tbody = document.getElementById('cveDevicesTableBody');
        if (uniqueDevices.length > 0) {
            tbody.innerHTML = uniqueDevices.map(device => {
                const riskLevel = (device.risk_level || '').toLowerCase();
                let riskClass = 'secondary';
                if (riskLevel === 'critical') riskClass = 'danger';
                else if (riskLevel === 'high') riskClass = 'warning';
                else if (riskLevel === 'medium') riskClass = 'info';
                else if (riskLevel === 'low') riskClass = 'success';

                const platformClass = (device.platform || '').toLowerCase() === 'ios' ? 'primary' : 'success';

                return `<tr>
                    <td><strong>${device.device_name || device.guid || 'Unknown'}</strong></td>
                    <td>${device.email || 'N/A'}</td>
                    <td><small>${device.model || ''}</small></td>
                    <td><span class="badge bg-${platformClass}">${device.platform || 'Unknown'}</span></td>
                    <td>${device.os_version || 'Unknown'}</td>
                    <td>${device.security_patch_level || 'N/A'}</td>
                    <td>${device.risk_level ? `<span class="badge bg-${riskClass}">${device.risk_level}</span>` : ''}</td>
                </tr>`;
            }).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No devices found</td></tr>';
        }

        // Store current CVE data for export
        this.currentCveDetails = {
            cve: cveName,
            devices: uniqueDevices
        };
    }

    deduplicateDevices(devices) {
        // Deduplicate by device GUID
        const seen = new Set();
        return devices.filter(device => {
            const id = device.guid || device.customer_device_id;
            if (seen.has(id)) {
                return false;
            }
            seen.add(id);
            return true;
        });
    }

    exportCveDevices() {
        if (!this.currentCveDetails) {
            this.showError('Export Error', 'No CVE data available to export');
            return;
        }

        const { cve, devices } = this.currentCveDetails;

        // Create CSV content
        const headers = ['Device Name', 'User Email', 'Platform', 'OS Version', 'Security Patch', 'Manufacturer', 'Model', 'Device Group', 'Last Checkin'];
        const rows = devices.map(device => [
            device.customer_device_id || device.guid || 'Unknown',
            device.email || 'N/A',
            device.platform || 'Unknown',
            device.os_version || 'Unknown',
            device.security_patch_level || 'N/A',
            device.manufacturer || 'N/A',
            device.model || 'N/A',
            device.device_group_name || 'N/A',
            device.last_checkin || 'N/A'
        ]);

        // Combine headers and rows
        const csvContent = [headers, ...rows]
            .map(row => row.map(field => `"${String(field).replace(/"/g, '""')}"`).join(','))
            .join('\n');

        // Create blob and download
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${cve}_affected_devices_${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);

        console.log(`Exported ${devices.length} devices for ${cve}`);
    }

    async exportReport() {
        const severityFilter = document.getElementById('cveSeverityFilter').value;

        try {
            // Disable button while exporting
            const exportBtn = document.getElementById('exportCveReportBtn');
            exportBtn.disabled = true;
            exportBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Generating...';

            const response = await fetch(`/api/cve/export/excel?min_severity=${severityFilter}`);

            if (!response.ok) {
                throw new Error(`Export failed: ${response.statusText}`);
            }

            // Download file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `cve_report_${new Date().toISOString().split('T')[0]}.xlsx`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            // Re-enable button
            exportBtn.disabled = false;
            exportBtn.innerHTML = '<i class="fas fa-file-excel me-1"></i>Export CVE Report';

        } catch (error) {
            console.error('CVE export error:', error);
            this.showError('Export Failed', error.message);

            // Re-enable button
            const exportBtn = document.getElementById('exportCveReportBtn');
            exportBtn.disabled = false;
            exportBtn.innerHTML = '<i class="fas fa-file-excel me-1"></i>Export CVE Report';
        }
    }

    async checkCacheStatus() {
        try {
            const response = await fetch('/api/cache/stats');
            if (response.ok) {
                const stats = await response.json();
                return {
                    hasDevices: stats.cached_devices > 0,
                    deviceCount: stats.cached_devices || 0,
                    cacheAge: stats.cache_age_minutes || 0
                };
            }
        } catch (error) {
            console.error('Failed to check cache status:', error);
        }
        return { hasDevices: false, deviceCount: 0, cacheAge: 0 };
    }

    showError(title, message) {
        const modal = new bootstrap.Modal(document.getElementById('errorModal'));
        document.getElementById('errorMessage').textContent = message;
        modal.show();
    }
}

// Initialize CVE Scanner
let cveScanner;

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new Dashboard();
    cveScanner = new CVEScanner();
});

// Handle page visibility change for auto-refresh
document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
        // Page became visible, could trigger refresh
        console.log('Page became visible - consider refreshing data');
    }
});