/**
 * Scheduling API Module
 * Handles all API calls related to scheduling functionality
 */

class SchedulingAPI extends BaseAPI {
    constructor() {
        super('Scheduling');
    }
    
    // Schedule Management
    async createSchedule(scheduleData) {
        this.log('Creating new schedule...');
        const result = await this.post('/schedule/create', scheduleData);
        this.log('Schedule created successfully', 'success');
        return result;
    }
    
    async getSchedule(scheduleId) {
        this.log(`Fetching schedule ${scheduleId}...`);
        return await this.get(`/schedule/${scheduleId}`);
    }
    
    async listSchedules() {
        this.log('Fetching all schedules...');
        return await this.get('/schedules');
    }
    
    async deleteSchedule(scheduleId) {
        this.log(`Deleting schedule ${scheduleId}...`);
        const result = await this.delete(`/schedule/${scheduleId}`);
        this.log('Schedule deleted successfully', 'success');
        return result;
    }
    
    async deleteAllSchedules() {
        this.log('Deleting all schedules...', 'warning');
        const result = await this.delete('/schedules/all');
        this.log('All schedules deleted', 'success');
        return result;
    }
    
    // Schedule Items
    async toggleItemAvailability(scheduleId, itemId, available) {
        this.log(`Toggling item ${itemId} availability to ${available}...`);
        return await this.put(`/schedule/${scheduleId}/item/${itemId}/availability`, { available });
    }
    
    async deleteScheduleItem(scheduleId, itemId) {
        this.log(`Deleting item ${itemId} from schedule ${scheduleId}...`);
        return await this.delete(`/schedule/${scheduleId}/item/${itemId}`);
    }
    
    async moveScheduleItem(scheduleId, itemIndex, direction) {
        this.log(`Moving item at index ${itemIndex} ${direction}...`);
        return await this.put(`/schedule/${scheduleId}/item/${itemIndex}/move`, { direction });
    }
    
    // Export/Import
    async exportSchedule(scheduleId, exportConfig) {
        this.log(`Exporting schedule ${scheduleId}...`);
        const result = await this.post(`/schedule/${scheduleId}/export`, exportConfig);
        this.log('Schedule exported successfully', 'success');
        return result;
    }
    
    async loadScheduleFromFTP(server, path, filename, date) {
        this.log(`Loading schedule from FTP: ${filename}...`);
        return await this.post('/schedule/load-from-ftp', {
            server,
            path,
            filename,
            date
        });
    }
    
    // Available Content
    async getAvailableContent(filters = {}) {
        this.log('Loading available content...');
        return await this.post('/content/available', filters);
    }
    
    // Schedule Configuration
    async getScheduleConfig() {
        this.log('Loading schedule configuration...');
        return await this.get('/schedule/config');
    }
    
    async saveScheduleConfig(config) {
        this.log('Saving schedule configuration...');
        return await this.post('/schedule/config', config);
    }
}

// Create singleton instance
const schedulingAPI = new SchedulingAPI();

// Export to global scope
window.schedulingAPI = schedulingAPI;