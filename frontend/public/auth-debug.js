// Enhanced Authentication Debugging Utility
// This script helps diagnose authentication issues in real-time

class AuthDebugger {
    constructor() {
        this.logs = [];
        this.maxLogs = 100;
        this.startTime = Date.now();
        this.init();
    }

    init() {
        this.log('AUTH_DEBUG', 'Authentication debugger initialized');
        this.monitorLocalStorage();
        this.monitorNetworkRequests();
        this.setupConsoleCommands();
    }

    log(category, message, data = null) {
        const timestamp = new Date().toISOString();
        const logEntry = {
            timestamp,
            category,
            message,
            data,
            timeFromStart: Date.now() - this.startTime
        };
        
        this.logs.push(logEntry);
        
        // Keep only recent logs
        if (this.logs.length > this.maxLogs) {
            this.logs.shift();
        }

        // Console output with color coding
        const colors = {
            AUTH_DEBUG: 'color: #2196F3',
            TOKEN_STORAGE: 'color: #4CAF50',
            API_REQUEST: 'color: #FF9800',
            ERROR: 'color: #F44336; font-weight: bold',
            SUCCESS: 'color: #4CAF50; font-weight: bold'
        };

        console.log(
            `%c[${category}] ${message}`,
            colors[category] || 'color: #666',
            data || ''
        );
    }

    monitorLocalStorage() {
        const originalSetItem = localStorage.setItem;
        const originalRemoveItem = localStorage.removeItem;
        const originalGetItem = localStorage.getItem;
        
        localStorage.setItem = (key, value) => {
            if (key.includes('pinnacle') || key.includes('auth')) {
                this.log('TOKEN_STORAGE', `Set: ${key}`, {
                    key,
                    valueLength: value ? value.length : 0,
                    valuePreview: value ? value.substring(0, 50) + '...' : null
                });
            }
            return originalSetItem.call(localStorage, key, value);
        };

        localStorage.removeItem = (key) => {
            if (key.includes('pinnacle') || key.includes('auth')) {
                this.log('TOKEN_STORAGE', `Remove: ${key}`, { key });
            }
            return originalRemoveItem.call(localStorage, key);
        };

        localStorage.getItem = (key) => {
            const value = originalGetItem.call(localStorage, key);
            if (key.includes('pinnacle') || key.includes('auth')) {
                this.log('TOKEN_STORAGE', `Get: ${key}`, {
                    key,
                    found: !!value,
                    valueLength: value ? value.length : 0
                });
            }
            return value;
        };
    }

    monitorNetworkRequests() {
        const originalFetch = window.fetch;
        
        window.fetch = async (...args) => {
            const [url, options] = args;
            const startTime = Date.now();
            
            if (url.includes('/api/')) {
                this.log('API_REQUEST', `Starting: ${url}`, {
                    url,
                    method: options?.method || 'GET',
                    headers: options?.headers,
                    hasAuth: !!(options?.headers?.Authorization)
                });
            }
            
            try {
                const response = await originalFetch.apply(window, args);
                const duration = Date.now() - startTime;
                
                if (url.includes('/api/')) {
                    this.log('API_REQUEST', `Completed: ${url}`, {
                        url,
                        status: response.status,
                        statusText: response.statusText,
                        duration: `${duration}ms`,
                        success: response.ok
                    });
                }
                
                return response;
            } catch (error) {
                const duration = Date.now() - startTime;
                
                if (url.includes('/api/')) {
                    this.log('ERROR', `Failed: ${url}`, {
                        url,
                        error: error.message,
                        duration: `${duration}ms`
                    });
                }
                
                throw error;
            }
        };
    }

    setupConsoleCommands() {
        // Make debugging commands available in console
        window.authDebug = {
            getLogs: () => this.logs,
            getRecentLogs: (count = 20) => this.logs.slice(-count),
            clearLogs: () => {
                this.logs = [];
                this.log('AUTH_DEBUG', 'Logs cleared');
            },
            checkToken: () => {
                const token = localStorage.getItem('pinnacle_auth_token');
                const dealerInfo = localStorage.getItem('pinnacle_dealer_info');
                
                this.log('AUTH_DEBUG', 'Token check results', {
                    hasToken: !!token,
                    tokenLength: token ? token.length : 0,
                    tokenPreview: token ? token.substring(0, 20) + '...' : null,
                    hasDealerInfo: !!dealerInfo,
                    dealerInfo: dealerInfo ? JSON.parse(dealerInfo) : null
                });
                
                return {
                    hasToken: !!token,
                    tokenLength: token ? token.length : 0,
                    hasDealerInfo: !!dealerInfo
                };
            },
            testDashboardAPI: async () => {
                this.log('AUTH_DEBUG', 'Testing dashboard API...');
                
                const token = localStorage.getItem('pinnacle_auth_token');
                if (!token) {
                    this.log('ERROR', 'No auth token found');
                    return;
                }
                
                try {
                    const response = await fetch('/api/dashboard/profile', {
                        headers: {
                            'Authorization': `Bearer ${token}`
                        }
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        this.log('SUCCESS', 'Dashboard API test successful', data);
                        return data;
                    } else {
                        const errorText = await response.text();
                        this.log('ERROR', 'Dashboard API test failed', {
                            status: response.status,
                            statusText: response.statusText,
                            error: errorText
                        });
                    }
                } catch (error) {
                    this.log('ERROR', 'Dashboard API test error', {
                        error: error.message,
                        stack: error.stack
                    });
                }
            },
            exportLogs: () => {
                const exportData = {
                    timestamp: new Date().toISOString(),
                    userAgent: navigator.userAgent,
                    url: window.location.href,
                    logs: this.logs
                };
                
                const blob = new Blob([JSON.stringify(exportData, null, 2)], {
                    type: 'application/json'
                });
                
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `auth-debug-${Date.now()}.json`;
                a.click();
                URL.revokeObjectURL(url);
                
                this.log('AUTH_DEBUG', 'Logs exported');
            }
        };
        
        this.log('AUTH_DEBUG', 'Console commands available: authDebug.getLogs(), authDebug.checkToken(), authDebug.testDashboardAPI(), authDebug.exportLogs()');
    }

    // Real-time authentication monitoring
    startMonitoring() {
        this.log('AUTH_DEBUG', 'Starting real-time monitoring...');
        
        // Check token every 5 seconds
        this.tokenCheckInterval = setInterval(() => {
            const token = localStorage.getItem('pinnacle_auth_token');
            if (!token) {
                this.log('ERROR', 'Token missing during monitoring');
            }
        }, 5000);
        
        // Monitor page visibility changes
        document.addEventListener('visibilitychange', () => {
            this.log('AUTH_DEBUG', 'Page visibility changed', {
                hidden: document.hidden
            });
        });
        
        // Monitor storage events (from other tabs)
        window.addEventListener('storage', (e) => {
            if (e.key && e.key.includes('pinnacle')) {
                this.log('TOKEN_STORAGE', 'Storage event from another tab', {
                    key: e.key,
                    oldValue: e.oldValue ? e.oldValue.substring(0, 20) + '...' : null,
                    newValue: e.newValue ? e.newValue.substring(0, 20) + '...' : null
                });
            }
        });
    }

    stopMonitoring() {
        if (this.tokenCheckInterval) {
            clearInterval(this.tokenCheckInterval);
            this.log('AUTH_DEBUG', 'Monitoring stopped');
        }
    }
}

// Auto-initialize if in development or if debug flag is set
if (window.location.hostname === 'localhost' || window.location.search.includes('debug=1')) {
    window.authDebugger = new AuthDebugger();
    window.authDebugger.startMonitoring();
}
