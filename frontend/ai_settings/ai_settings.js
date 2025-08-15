/**
 * AI Settings Module
 * Handles AI provider configuration and analysis settings
 */

// AI Settings State
const aiSettingsState = {
    enabled: false,
    transcriptionOnly: false,
    provider: 'openai',
    model: 'gpt-3.5-turbo',
    openaiApiKey: '',
    anthropicApiKey: '',
    maxChunkSize: 4000,
    apiKeysValid: {
        openai: false,
        anthropic: false
    }
};

// Initialize AI Settings Module
function aiSettingsInit() {
    console.log('Initializing AI Settings module...');
    
    // Load saved settings
    aiSettingsLoadConfig();
    
    // Set up event listeners
    aiSettingsSetupEventListeners();
    
    // Update AppState
    AppState.setModule('ai_settings', aiSettingsState);
}

// Set up event listeners
function aiSettingsSetupEventListeners() {
    // Checkboxes
    const aiEnabledCheckbox = document.getElementById('aiEnabled');
    if (aiEnabledCheckbox) {
        aiEnabledCheckbox.addEventListener('change', aiSettingsHandleToggle);
    }
    
    const transcriptionCheckbox = document.getElementById('transcriptionOnly');
    if (transcriptionCheckbox) {
        transcriptionCheckbox.addEventListener('change', aiSettingsHandleTranscriptionToggle);
    }
    
    // Dropdowns
    const providerSelect = document.getElementById('aiProvider');
    if (providerSelect) {
        providerSelect.addEventListener('change', aiSettingsHandleProviderChange);
    }
    
    const modelSelect = document.getElementById('aiModel');
    if (modelSelect) {
        modelSelect.addEventListener('change', aiSettingsHandleModelChange);
    }
    
    // API Keys
    const openaiKeyInput = document.getElementById('openaiApiKey');
    if (openaiKeyInput) {
        openaiKeyInput.addEventListener('change', aiSettingsHandleApiKeyChange);
        openaiKeyInput.addEventListener('blur', () => aiSettingsValidateApiKey('openai'));
    }
    
    const anthropicKeyInput = document.getElementById('anthropicApiKey');
    if (anthropicKeyInput) {
        anthropicKeyInput.addEventListener('change', aiSettingsHandleApiKeyChange);
        anthropicKeyInput.addEventListener('blur', () => aiSettingsValidateApiKey('anthropic'));
    }
    
    // Max Chunk Size
    const chunkSizeInput = document.getElementById('maxChunkSize');
    if (chunkSizeInput) {
        chunkSizeInput.addEventListener('change', aiSettingsHandleChunkSizeChange);
    }
}

// Load configuration
async function aiSettingsLoadConfig() {
    try {
        const response = await window.API.get('/config');
        if (response.success && response.config) {
            const config = response.config;
            
            // Update AI settings from config
            if (config.ai_settings) {
                Object.assign(aiSettingsState, config.ai_settings);
            }
            
            // Load API keys from environment
            await aiSettingsLoadApiKeys();
            
            // Update UI
            aiSettingsUpdateUI();
        }
    } catch (error) {
        console.error('Failed to load AI settings:', error);
    }
}

// Load API keys from environment
async function aiSettingsLoadApiKeys() {
    try {
        const response = await window.API.get('/ai/api-keys');
        if (response.success) {
            if (response.openai_key) {
                aiSettingsState.openaiApiKey = response.openai_key;
                aiSettingsState.apiKeysValid.openai = true;
            }
            if (response.anthropic_key) {
                aiSettingsState.anthropicApiKey = response.anthropic_key;
                aiSettingsState.apiKeysValid.anthropic = true;
            }
        }
    } catch (error) {
        console.error('Failed to load API keys:', error);
    }
}

// Update UI with current settings
function aiSettingsUpdateUI() {
    // Update checkboxes
    const aiEnabledCheckbox = document.getElementById('aiEnabled');
    if (aiEnabledCheckbox) aiEnabledCheckbox.checked = aiSettingsState.enabled;
    
    const transcriptionCheckbox = document.getElementById('transcriptionOnly');
    if (transcriptionCheckbox) transcriptionCheckbox.checked = aiSettingsState.transcriptionOnly;
    
    // Update dropdowns
    const providerSelect = document.getElementById('aiProvider');
    if (providerSelect) providerSelect.value = aiSettingsState.provider;
    
    const modelSelect = document.getElementById('aiModel');
    if (modelSelect) modelSelect.value = aiSettingsState.model;
    
    // Update API keys (masked)
    const openaiKeyInput = document.getElementById('openaiApiKey');
    if (openaiKeyInput && aiSettingsState.openaiApiKey) {
        openaiKeyInput.value = aiSettingsMaskApiKey(aiSettingsState.openaiApiKey);
    }
    
    const anthropicKeyInput = document.getElementById('anthropicApiKey');
    if (anthropicKeyInput && aiSettingsState.anthropicApiKey) {
        anthropicKeyInput.value = aiSettingsMaskApiKey(aiSettingsState.anthropicApiKey);
    }
    
    // Update chunk size
    const chunkSizeInput = document.getElementById('maxChunkSize');
    if (chunkSizeInput) chunkSizeInput.value = aiSettingsState.maxChunkSize;
    
    // Update status display
    aiSettingsUpdateStatus();
}

// Handle AI toggle
function aiSettingsHandleToggle(event) {
    aiSettingsState.enabled = event.target.checked;
    aiSettingsUpdateStatus();
    aiSettingsSaveConfig();
    
    if (aiSettingsState.enabled) {
        window.showNotification('AI analysis enabled', 'success');
    } else {
        window.showNotification('AI analysis disabled', 'info');
    }
}

// Handle transcription toggle
function aiSettingsHandleTranscriptionToggle(event) {
    aiSettingsState.transcriptionOnly = event.target.checked;
    aiSettingsSaveConfig();
    
    if (aiSettingsState.transcriptionOnly) {
        window.showNotification('Transcription-only mode enabled', 'info');
    } else {
        window.showNotification('Full AI analysis mode enabled', 'info');
    }
}

// Handle provider change
function aiSettingsHandleProviderChange(event) {
    aiSettingsState.provider = event.target.value;
    aiSettingsUpdateModelOptions();
    aiSettingsSaveConfig();
}

// Handle model change
function aiSettingsHandleModelChange(event) {
    aiSettingsState.model = event.target.value;
    aiSettingsSaveConfig();
}

// Handle API key change
function aiSettingsHandleApiKeyChange(event) {
    const input = event.target;
    const provider = input.id.includes('openai') ? 'openai' : 'anthropic';
    const value = input.value;
    
    // Don't update if it's a masked value
    if (value.includes('•••')) return;
    
    aiSettingsState[`${provider}ApiKey`] = value;
}

// Handle chunk size change
function aiSettingsHandleChunkSizeChange(event) {
    aiSettingsState.maxChunkSize = parseInt(event.target.value) || 4000;
    aiSettingsSaveConfig();
}

// Update model options based on provider
function aiSettingsUpdateModelOptions() {
    const modelSelect = document.getElementById('aiModel');
    if (!modelSelect) return;
    
    const models = {
        openai: [
            { value: 'gpt-3.5-turbo', text: 'GPT-3.5 Turbo' },
            { value: 'gpt-4', text: 'GPT-4' }
        ],
        anthropic: [
            { value: 'claude-3-sonnet-20240229', text: 'Claude 3 Sonnet' },
            { value: 'claude-3-opus-20240229', text: 'Claude 3 Opus' }
        ]
    };
    
    // Clear current options
    modelSelect.innerHTML = '';
    
    // Add new options
    const providerModels = models[aiSettingsState.provider] || [];
    providerModels.forEach(model => {
        const option = document.createElement('option');
        option.value = model.value;
        option.textContent = model.text;
        modelSelect.appendChild(option);
    });
    
    // Set default model for provider
    if (providerModels.length > 0) {
        aiSettingsState.model = providerModels[0].value;
        modelSelect.value = aiSettingsState.model;
    }
}

// Validate API key
async function aiSettingsValidateApiKey(provider) {
    const key = aiSettingsState[`${provider}ApiKey`];
    if (!key || key.includes('•••')) return;
    
    try {
        const response = await window.API.post('/ai/validate-key', {
            provider: provider,
            api_key: key
        });
        
        aiSettingsState.apiKeysValid[provider] = response.success;
        aiSettingsUpdateApiKeyStatus(provider, response.success);
        
        if (response.success) {
            window.showNotification(`${provider} API key is valid`, 'success');
        } else {
            window.showNotification(`Invalid ${provider} API key`, 'error');
        }
    } catch (error) {
        aiSettingsState.apiKeysValid[provider] = false;
        aiSettingsUpdateApiKeyStatus(provider, false);
    }
}

// Update API key status indicator
function aiSettingsUpdateApiKeyStatus(provider, isValid) {
    const statusEl = document.querySelector(`#${provider}ApiKey + .ai-settings-api-key-status`);
    if (statusEl) {
        statusEl.className = `ai-settings-api-key-status ${isValid ? 'valid' : 'invalid'}`;
        statusEl.innerHTML = isValid ? '<i class="fas fa-check-circle"></i>' : '<i class="fas fa-times-circle"></i>';
    }
}

// Update status display
function aiSettingsUpdateStatus() {
    const statusEl = document.querySelector('.ai-settings-status');
    if (!statusEl) return;
    
    if (aiSettingsState.enabled) {
        statusEl.className = 'ai-settings-status enabled';
        statusEl.innerHTML = '<i class="fas fa-check-circle"></i> AI Analysis Enabled';
    } else {
        statusEl.className = 'ai-settings-status disabled';
        statusEl.innerHTML = '<i class="fas fa-times-circle"></i> AI Analysis Disabled';
    }
}

// Save configuration
async function aiSettingsSaveConfig() {
    try {
        const config = {
            ai_settings: {
                enabled: aiSettingsState.enabled,
                transcriptionOnly: aiSettingsState.transcriptionOnly,
                provider: aiSettingsState.provider,
                model: aiSettingsState.model,
                maxChunkSize: aiSettingsState.maxChunkSize
            }
        };
        
        // Save API keys separately
        if (aiSettingsState.openaiApiKey && !aiSettingsState.openaiApiKey.includes('•••')) {
            await window.API.post('/ai/api-keys', {
                openai_key: aiSettingsState.openaiApiKey,
                anthropic_key: aiSettingsState.anthropicApiKey
            });
        }
        
        await window.API.post('/config', config);
        console.log('AI settings saved successfully');
        
        // Update AppState
        AppState.setModule('ai_settings', aiSettingsState);
    } catch (error) {
        console.error('Failed to save AI settings:', error);
        window.showNotification('Failed to save AI settings', 'error');
    }
}

// Test AI connection
async function aiSettingsTestConnection() {
    const provider = aiSettingsState.provider;
    const apiKey = aiSettingsState[`${provider}ApiKey`];
    
    if (!apiKey) {
        window.showNotification('Please enter an API key first', 'warning');
        return;
    }
    
    const button = event.target;
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Testing...';
    
    try {
        const response = await window.API.post('/ai/test-connection', {
            provider: provider,
            api_key: apiKey,
            model: aiSettingsState.model
        });
        
        if (response.success) {
            window.showNotification('AI connection successful!', 'success');
            aiSettingsDisplayTestResults(response.result);
        } else {
            throw new Error(response.message);
        }
    } catch (error) {
        window.showNotification(`AI connection failed: ${error.message}`, 'error');
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-vial"></i> Test AI Connection';
    }
}

// Display test results
function aiSettingsDisplayTestResults(result) {
    const resultsEl = document.querySelector('.ai-settings-test-results');
    if (resultsEl) {
        resultsEl.textContent = JSON.stringify(result, null, 2);
        resultsEl.style.display = 'block';
    }
}

// Mask API key for display
function aiSettingsMaskApiKey(key) {
    if (!key) return '';
    const visibleChars = 4;
    const maskedLength = key.length - visibleChars;
    return key.substring(0, visibleChars) + '•'.repeat(Math.max(maskedLength, 20));
}

// Export functions to global scope
window.aiSettingsInit = aiSettingsInit;
window.aiSettingsSaveConfig = aiSettingsSaveConfig;
window.aiSettingsLoadConfig = aiSettingsLoadConfig;
window.aiSettingsTestConnection = aiSettingsTestConnection;
window.saveAISettings = aiSettingsSaveConfig; // Legacy support
window.loadAISettings = aiSettingsLoadConfig; // Legacy support
window.testAIConnection = aiSettingsTestConnection; // Legacy support