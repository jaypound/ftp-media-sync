/**
 * Base API Module
 * Provides common API functionality and error handling
 */

class BaseAPI {
    constructor(module) {
        this.module = module;
        this.baseURL = window.APIConfig ? window.APIConfig.baseURL : 
            (window.location.port === '8000' ? 'http://127.0.0.1:5000/api' : '/api');
    }
    
    // Log function
    log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const prefix = `[${this.module}] ${timestamp}`;
        
        switch(type) {
            case 'error':
                console.error(`${prefix} ❌ ${message}`);
                break;
            case 'success':
                console.log(`${prefix} ✅ ${message}`);
                break;
            case 'warning':
                console.warn(`${prefix} ⚠️ ${message}`);
                break;
            default:
                console.log(`${prefix} ℹ️ ${message}`);
        }
    }
    
    // Show notification
    showNotification(message, type = 'info', duration = 3000) {
        if (window.showNotification) {
            window.showNotification(message, type, duration);
        }
    }
    
    // Handle API errors
    handleError(error, context) {
        this.log(`${context}: ${error.message}`, 'error');
        this.showNotification(`Error: ${error.message}`, 'error');
        throw error;
    }
    
    // Make API request with error handling
    async request(method, endpoint, data = null) {
        try {
            const result = await window.API.request(method, endpoint, data);
            return result;
        } catch (error) {
            this.handleError(error, `${method} ${endpoint}`);
        }
    }
    
    // Convenience methods
    async get(endpoint) {
        return this.request('GET', endpoint);
    }
    
    async post(endpoint, data) {
        return this.request('POST', endpoint, data);
    }
    
    async put(endpoint, data) {
        return this.request('PUT', endpoint, data);
    }
    
    async delete(endpoint) {
        return this.request('DELETE', endpoint);
    }
}

// Export to global scope
window.BaseAPI = BaseAPI;