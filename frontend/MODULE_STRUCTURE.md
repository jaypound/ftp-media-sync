# FTP Media Sync Module Structure

## Overview
The application has been restructured into a modular architecture where each major feature is contained in its own module with dedicated CSS, JavaScript, and API files.

## Directory Structure
```
frontend/
├── api/                    # API layer modules
│   ├── base.api.js        # Base API class with error handling
│   └── scheduling.api.js  # Scheduling-specific API calls
├── dashboard/             # Dashboard module
│   ├── dashboard.css      # Dashboard-specific styles
│   └── dashboard.js       # Dashboard functionality
├── scheduling/            # Scheduling module
│   ├── scheduling.css     # Scheduling-specific styles
│   └── scheduling.js      # Scheduling functionality
├── servers/               # Server configuration module
│   ├── servers.css        # Server panel styles
│   └── servers.js         # Server connection logic
├── settings/              # Settings module
├── ai_settings/           # AI Settings module
├── admin/                 # Administration module
├── fill_graphics/         # Fill Graphics module
├── meeting_schedule/      # Meeting Schedule module
├── main.js               # Module loader and AppState manager
├── script.js             # Legacy code (being migrated)
├── styles.css            # Global styles
└── index.html            # Main application HTML

```

## Naming Conventions

### CSS Classes
- Module-specific classes: `moduleName-component-element`
- Examples:
  - `dashboard-stat-card`
  - `scheduling-schedule-header`
  - `servers-connection-status`

### JavaScript Functions
- Module functions: `moduleNameFunctionName`
- Examples:
  - `dashboardUpdateStats()`
  - `schedulingDisplayScheduleDetails()`
  - `serversTestConnection()`

### Files
- Module files: `module_name.ext` (snake_case)
- API files: `module_name.api.js`

## Module Structure

Each module follows this structure:

### CSS File (`module_name.css`)
```css
/* Module Name CSS */
/* All classes prefixed with 'moduleName-' to avoid conflicts */

.moduleName-component {
    /* styles */
}
```

### JavaScript File (`module_name.js`)
```javascript
/**
 * Module Name
 * Brief description
 */

// Module State
const moduleNameState = {
    // state properties
};

// Initialize Module
function moduleNameInit() {
    console.log('Initializing ModuleName module...');
    // initialization code
}

// Module functions
function moduleNameDoSomething() {
    // function code
}

// Export to global scope
window.moduleNameInit = moduleNameInit;
window.moduleNameDoSomething = moduleNameDoSomething;
```

### API File (`api/module_name.api.js`)
```javascript
/**
 * Module Name API
 * Handles all API calls for module
 */

class ModuleNameAPI extends BaseAPI {
    constructor() {
        super('ModuleName');
    }
    
    async someApiCall() {
        return await this.post('/endpoint', data);
    }
}

const moduleNameAPI = new ModuleNameAPI();
window.moduleNameAPI = moduleNameAPI;
```

## AppState Manager

The `AppState` object in `main.js` manages global application state:

```javascript
// Get module state
const dashboardState = AppState.getModule('dashboard');

// Set module state
AppState.setModule('dashboard', { connected: true });

// Listen for state changes
AppState.on('stateChanged', (data) => {
    console.log(`Module ${data.module} state changed`);
});

// Get/set current panel
AppState.setCurrentPanel('dashboard');
const currentPanel = AppState.getCurrentPanel();
```

## Module Loader

The `ModuleLoader` in `main.js` handles dynamic loading of modules:

```javascript
// Load a specific module
await ModuleLoader.loadModule('dashboard');

// Module configuration
ModuleLoader.moduleConfig = {
    'dashboard': {
        css: 'dashboard/dashboard.css',
        js: 'dashboard/dashboard.js',
        init: 'dashboardInit'
    }
};
```

## Migration Strategy

1. **Phase 1**: Create module structure (COMPLETED)
   - Set up directory structure
   - Create main.js with ModuleLoader
   - Create base API layer

2. **Phase 2**: Migrate existing features (IN PROGRESS)
   - Extract feature-specific code from script.js
   - Create module-specific CSS with proper prefixes
   - Update HTML to use new classes

3. **Phase 3**: Complete modularization
   - Remove redundant code from script.js
   - Create shared components library
   - Implement build process

## Best Practices

1. **Isolation**: Each module should be self-contained
2. **Prefixing**: Always prefix CSS classes and JS functions
3. **State Management**: Use AppState for cross-module communication
4. **API Calls**: Use the API layer for all backend communication
5. **Documentation**: Document module interfaces and dependencies
6. **Testing**: Test modules independently before integration

## Adding a New Module

1. Create module directory: `frontend/module_name/`
2. Create CSS file with prefixed classes
3. Create JS file with initialization function
4. Add module to `ModuleLoader.moduleConfig`
5. Add CSS/JS references to index.html
6. Create API file if needed
7. Update this documentation