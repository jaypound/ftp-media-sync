/**
 * Servers Module
 * Handles server configuration and connection management
 */

// Servers State
const serversState = {
    source: {
        host: '',
        port: 21,
        user: '',
        pass: '',
        path: '/mnt/main/ATL26 On-Air Content',
        connected: false,
        testing: false
    },
    target: {
        host: '',
        port: 21,
        user: '',
        pass: '',
        path: '/mnt/main/ATL26 On-Air Content',
        connected: false,
        testing: false
    }
};

// Initialize Servers Module
function serversInit() {
    console.log('Initializing Servers module...');
    
    // Load saved configuration
    serversLoadConfig();
    
    // Set up event listeners
    serversSetupEventListeners();
    
    // Update AppState
    AppState.setModule('servers', {
        sourceConnected: serversState.source.connected,
        targetConnected: serversState.target.connected
    });
}

// Set up event listeners
function serversSetupEventListeners() {
    // Password visibility toggles
    const passwordToggles = document.querySelectorAll('.servers-password-toggle');
    passwordToggles.forEach(toggle => {
        toggle.addEventListener('click', serversTogglePasswordVisibility);
    });
    
    // Auto-save on input change
    const inputs = document.querySelectorAll('.servers-form-control');
    inputs.forEach(input => {
        input.addEventListener('change', serversHandleInputChange);
    });
}

// Load configuration
async function serversLoadConfig() {
    try {
        const response = await window.API.get('/config');
        if (response.success && response.config) {
            const config = response.config;
            
            // Update source server
            if (config.source_server) {
                serversState.source = {
                    ...serversState.source,
                    ...config.source_server,
                    pass: '' // Don't load password
                };
                serversUpdateForm('source');
            }
            
            // Update target server
            if (config.target_server) {
                serversState.target = {
                    ...serversState.target,
                    ...config.target_server,
                    pass: '' // Don't load password
                };
                serversUpdateForm('target');
            }
        }
        
        // Check actual connection status from backend
        await serversCheckConnectionStatus();
    } catch (error) {
        console.error('Failed to load server config:', error);
    }
}

// Update form with server data
function serversUpdateForm(serverType) {
    const server = serversState[serverType];
    
    // Update input fields
    const hostInput = document.getElementById(`${serverType}Host`);
    if (hostInput) hostInput.value = server.host;
    
    const portInput = document.getElementById(`${serverType}Port`);
    if (portInput) portInput.value = server.port;
    
    const userInput = document.getElementById(`${serverType}User`);
    if (userInput) userInput.value = server.user;
    
    const pathInput = document.getElementById(`${serverType}Path`);
    if (pathInput) pathInput.value = server.path;
    
    // Update connection status
    serversUpdateConnectionStatus(serverType, server.connected ? 'connected' : 'disconnected');
}

// Handle input changes
function serversHandleInputChange(event) {
    const input = event.target;
    const id = input.id;
    
    // Determine server type and field
    const serverType = id.startsWith('source') ? 'source' : 'target';
    const field = id.replace(serverType, '').toLowerCase();
    
    // Update state
    if (field === 'port') {
        serversState[serverType][field] = parseInt(input.value) || 21;
    } else {
        serversState[serverType][field] = input.value;
    }
    
    // Auto-save configuration
    serversSaveConfig();
}

// Save configuration
async function serversSaveConfig() {
    try {
        const config = {
            source_server: {
                host: serversState.source.host,
                port: serversState.source.port,
                user: serversState.source.user,
                path: serversState.source.path
            },
            target_server: {
                host: serversState.target.host,
                port: serversState.target.port,
                user: serversState.target.user,
                path: serversState.target.path
            }
        };
        
        await window.API.post('/config', config);
        console.log('Server configuration saved');
    } catch (error) {
        console.error('Failed to save server config:', error);
    }
}

// Test connection
async function serversTestConnection(serverType) {
    if (serversState[serverType].testing) return;
    
    const server = serversState[serverType];
    const button = document.getElementById(`${serverType}TestBtn`);
    
    // Get password from input
    const passInput = document.getElementById(`${serverType}Pass`);
    if (passInput) {
        server.pass = passInput.value;
    }
    
    // Validate inputs
    if (!server.host || !server.user || !server.pass) {
        window.showNotification('Please fill in all server details', 'error');
        return;
    }
    
    // Update UI
    serversState[serverType].testing = true;
    serversUpdateConnectionStatus(serverType, 'connecting');
    if (button) {
        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Testing...';
    }
    
    try {
        const response = await window.API.post('/test-connection', {
            server_type: serverType,
            host: server.host,
            port: server.port,
            user: server.user,
            password: server.pass,
            path: server.path
        });
        
        if (response.success) {
            serversState[serverType].connected = true;
            serversUpdateConnectionStatus(serverType, 'connected');
            window.showNotification(`${serverType} server connected successfully`, 'success');
            
            // Update AppState
            AppState.setModule('servers', {
                [`${serverType}Connected`]: true
            });
        } else {
            throw new Error(response.message || 'Connection failed');
        }
    } catch (error) {
        serversState[serverType].connected = false;
        serversUpdateConnectionStatus(serverType, 'disconnected');
        window.showNotification(`Failed to connect to ${serverType} server: ${error.message}`, 'error');
        
        // Update AppState
        AppState.setModule('servers', {
            [`${serverType}Connected`]: false
        });
    } finally {
        serversState[serverType].testing = false;
        if (button) {
            button.disabled = false;
            button.innerHTML = '<i class="fas fa-plug"></i> Test Connection';
        }
    }
}

// Update connection status UI
function serversUpdateConnectionStatus(serverType, status) {
    const statusEl = document.getElementById(`${serverType}Status`);
    const statusTextEl = document.getElementById(`${serverType}StatusText`);
    
    if (statusEl) {
        const statusText = status.charAt(0).toUpperCase() + status.slice(1);
        const statusIcon = {
            connected: '<i class="fas fa-check-circle"></i>',
            disconnected: '<i class="fas fa-times-circle"></i>',
            connecting: '<i class="fas fa-spinner fa-spin"></i>'
        }[status];
        
        statusEl.className = `servers-connection-status ${status}`;
        statusEl.innerHTML = `${statusIcon} ${statusText}`;
    }
    
    if (statusTextEl) {
        statusTextEl.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    }
}

// Toggle password visibility
function serversTogglePasswordVisibility(event) {
    const button = event.currentTarget;
    const input = button.previousElementSibling;
    
    if (input.type === 'password') {
        input.type = 'text';
        button.innerHTML = '<i class="fas fa-eye-slash"></i>';
    } else {
        input.type = 'password';
        button.innerHTML = '<i class="fas fa-eye"></i>';
    }
}

// Update path from select
function serversUpdatePath(serverType) {
    const selectEl = document.getElementById(`${serverType}PathSelect`);
    const inputEl = document.getElementById(`${serverType}Path`);
    
    if (selectEl && inputEl) {
        inputEl.value = selectEl.value;
        serversState[serverType].path = selectEl.value;
        serversSaveConfig();
    }
}

// Check connection status from backend
async function serversCheckConnectionStatus() {
    try {
        const response = await window.API.get('/connection-status');
        if (response.success && response.status) {
            // Update source connection status
            serversState.source.connected = response.status.source.connected;
            serversUpdateConnectionStatus('source', serversState.source.connected ? 'connected' : 'disconnected');
            
            // Update target connection status
            serversState.target.connected = response.status.target.connected;
            serversUpdateConnectionStatus('target', serversState.target.connected ? 'connected' : 'disconnected');
            
            // Update AppState
            AppState.setModule('servers', {
                sourceConnected: serversState.source.connected,
                targetConnected: serversState.target.connected
            });
        }
    } catch (error) {
        console.error('Failed to check connection status:', error);
    }
}

// Export functions to global scope
window.serversInit = serversInit;
window.serversTestConnection = serversTestConnection;
window.serversUpdatePath = serversUpdatePath;
window.serversCheckConnectionStatus = serversCheckConnectionStatus;
window.testConnection = serversTestConnection; // Legacy support