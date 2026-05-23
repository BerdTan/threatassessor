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
        let apiKey = localStorage.getItem('tm_api_key');

        if (!apiKey) {
            // Show better prompt
            apiKey = prompt(
                '🔑 API Key Required\n\n' +
                'Please enter your TM-API-KEY.\n\n' +
                'You can find this in your .env file:\n' +
                'API_KEY=your-key-here'
            );

            if (!apiKey) {
                const error = {
                    message: 'API key is required',
                    detail: 'Please provide a valid API key to use the ThreatAssessor API'
                };
                this.emit('error', error);
                return;
            }

            // Save for future requests
            localStorage.setItem('tm_api_key', apiKey);
            console.log('✅ API key saved to localStorage');
        }

        // Upload file and get streaming response
        try {
            console.log(`[SSE] Connecting to ${this.endpoint} with API key...`);

            const response = await fetch(this.endpoint, {
                method: 'POST',
                headers: {
                    'TM-API-KEY': apiKey
                },
                body: this.formData
            });

            if (!response.ok) {
                // Handle different error types
                let errorDetail = 'Request failed';

                try {
                    const error = await response.json();
                    errorDetail = error.detail || error.message || 'Request failed';
                } catch (e) {
                    errorDetail = `HTTP ${response.status}: ${response.statusText}`;
                }

                // If 401 Unauthorized, clear saved API key
                if (response.status === 401) {
                    console.error('❌ API key is invalid or missing');
                    localStorage.removeItem('tm_api_key');
                    errorDetail += '\n\nYour API key is invalid. Please check your .env file and try again.';
                }

                throw new Error(errorDetail);
            }

            console.log('✅ SSE connection established');

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
