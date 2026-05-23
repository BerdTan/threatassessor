// SSE Client for ThreatAssessor Dashboard

class SSEClient {
    constructor(endpoint, formData) {
        this.endpoint = endpoint;
        this.formData = formData;
        this.eventSource = null;
        this.listeners = {};
    }

    on(event, callback) {
        if (!this.listeners[event]) {
            this.listeners[event] = [];
        }
        this.listeners[event].push(callback);
    }

    emit(event, data) {
        if (this.listeners[event]) {
            this.listeners[event].forEach(callback => callback(data));
        }
    }

    async connect() {
        // Get API key from localStorage or prompt user
        const apiKey = localStorage.getItem('tm_api_key') || prompt('Enter TM-API-KEY:');
        if (!apiKey) {
            alert('API key is required');
            return;
        }
        localStorage.setItem('tm_api_key', apiKey);

        // Upload file and get streaming response
        try {
            const response = await fetch(this.endpoint, {
                method: 'POST',
                headers: {
                    'TM-API-KEY': apiKey
                },
                body: this.formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Request failed');
            }

            // Read SSE stream
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Process complete messages
                const messages = buffer.split('\n\n');
                buffer = messages.pop(); // Keep incomplete message

                for (const message of messages) {
                    if (!message.trim()) continue;

                    const lines = message.split('\n');
                    let event = 'message';
                    let data = '';

                    for (const line of lines) {
                        if (line.startsWith('event: ')) {
                            event = line.slice(7).trim();
                        } else if (line.startsWith('data: ')) {
                            data = line.slice(6).trim();
                        }
                    }

                    if (data) {
                        try {
                            const parsedData = JSON.parse(data);
                            this.emit(event, parsedData);
                        } catch (e) {
                            console.error('Failed to parse SSE data:', e, data);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('SSE connection failed:', error);
            this.emit('error', {
                message: 'Connection failed',
                detail: error.message
            });
        }
    }

    close() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }
}
