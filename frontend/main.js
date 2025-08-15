/**
 * Main Application Module Loader and State Manager
 * Handles loading of all modules and manages application state
 */

// Application State Manager
const AppState = {
    modules: {},
    config: {},
    currentPanel: 'dashboard',
    
    // Get module state
    getModule(name) {
        if (!this.modules[name]) {
            this.modules[name] = {};
        }
        return this.modules[name];
    },
    
    // Set module state
    setModule(name, state) {
        this.modules[name] = { ...this.modules[name], ...state };
        this.emit('stateChanged', { module: name, state: this.modules[name] });
    },
    
    // Event emitter functionality
    listeners: {},
    
    on(event, callback) {
        if (!this.listeners[event]) {
            this.listeners[event] = [];
        }
        this.listeners[event].push(callback);
    },
    
    emit(event, data) {
        if (this.listeners[event]) {
            this.listeners[event].forEach(callback => callback(data));
        }
    },
    
    // Panel management
    setCurrentPanel(panel) {
        this.currentPanel = panel;
        this.emit('panelChanged', panel);
    },
    
    getCurrentPanel() {
        return this.currentPanel;
    }
};

// Module Loader
const ModuleLoader = {
    loadedModules: new Set(),
    moduleConfig: {
        'dashboard': {
            init: 'dashboardInit'
        },
        'scheduling': {
            init: 'schedulingInit'
        },
        'servers': {
            init: 'serversInit'
        },
        'settings': {
            init: 'settingsInit'
        },
        'ai_settings': {
            init: 'aiSettingsInit'
        },
        'admin': {
            init: 'adminInit'
        },
        'meeting_schedule': {
            init: 'meetingScheduleInit'
        },
        'fill_graphics': {
            init: 'fillGraphicsInit'
        }
    },
    
    // Load CSS file
    loadCSS(href) {
        return new Promise((resolve, reject) => {
            // Check if already loaded
            if (document.querySelector(`link[href="${href}"]`)) {
                resolve();
                return;
            }
            
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = href;
            link.onload = resolve;
            link.onerror = reject;
            document.head.appendChild(link);
        });
    },
    
    // Load JS file
    loadJS(src) {
        return new Promise((resolve, reject) => {
            // Check if already loaded
            if (document.querySelector(`script[src="${src}"]`)) {
                resolve();
                return;
            }
            
            const script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = reject;
            document.body.appendChild(script);
        });
    },
    
    // Load a module
    async loadModule(moduleName) {
        if (this.loadedModules.has(moduleName)) {
            console.log(`Module ${moduleName} already loaded`);
            return;
        }
        
        const config = this.moduleConfig[moduleName];
        if (!config) {
            console.warn(`No configuration found for module: ${moduleName}`);
            return;
        }
        
        try {
            // Load CSS if exists
            if (config.css) {
                await this.loadCSS(config.css);
                console.log(`Loaded CSS for ${moduleName}`);
            }
            
            // Load JS if exists
            if (config.js) {
                await this.loadJS(config.js);
                console.log(`Loaded JS for ${moduleName}`);
            }
            
            // Initialize module if init function exists
            if (config.init && window[config.init]) {
                window[config.init]();
                console.log(`Initialized ${moduleName}`);
            }
            
            this.loadedModules.add(moduleName);
        } catch (error) {
            console.error(`Failed to load module ${moduleName}:`, error);
        }
    },
    
    // Load all modules
    async loadAllModules() {
        const modules = Object.keys(this.moduleConfig);
        // Initialize modules sequentially to avoid dependency issues
        for (const module of modules) {
            try {
                const config = this.moduleConfig[module];
                if (config.init && window[config.init]) {
                    window[config.init]();
                    console.log(`Initialized ${module}`);
                }
                this.loadedModules.add(module);
            } catch (error) {
                console.error(`Failed to initialize module ${module}:`, error);
            }
        }
        console.log('All modules initialized');
    }
};

// API Configuration
const APIConfig = {
    baseURL: 'http://127.0.0.1:5000/api',
    timeout: 30000,
    
    // Get full URL for an endpoint
    getURL(endpoint) {
        return `${this.baseURL}${endpoint}`;
    },
    
    // Default headers
    getHeaders() {
        return {
            'Content-Type': 'application/json'
        };
    }
};

// Base API Handler
const API = {
    // Make a request
    async request(method, endpoint, data = null) {
        const url = APIConfig.getURL(endpoint);
        const options = {
            method,
            headers: APIConfig.getHeaders()
        };
        
        if (data && method !== 'GET') {
            options.body = JSON.stringify(data);
        }
        
        try {
            const response = await fetch(url, options);
            const result = await response.json();
            
            if (!response.ok) {
                throw new Error(result.message || `HTTP ${response.status}`);
            }
            
            return result;
        } catch (error) {
            console.error(`API Error (${method} ${endpoint}):`, error);
            throw error;
        }
    },
    
    // Convenience methods
    get(endpoint) {
        return this.request('GET', endpoint);
    },
    
    post(endpoint, data) {
        return this.request('POST', endpoint, data);
    },
    
    put(endpoint, data) {
        return this.request('PUT', endpoint, data);
    },
    
    delete(endpoint) {
        return this.request('DELETE', endpoint);
    }
};

// Initialize application
async function initializeApp() {
    console.log('Initializing FTP Media Sync Application...');
    
    // Load all modules
    await ModuleLoader.loadAllModules();
    
    // Set up panel change listener
    AppState.on('panelChanged', (panel) => {
        console.log(`Panel changed to: ${panel}`);
    });
    
    // Initialize with dashboard
    AppState.setCurrentPanel('dashboard');
    
    console.log('Application initialized');
}

// Export to global scope for compatibility
window.AppState = AppState;
window.ModuleLoader = ModuleLoader;
window.API = API;
window.APIConfig = APIConfig;

// Start initialization when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}