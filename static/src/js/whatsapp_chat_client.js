// static/src/js/whatsapp_chat_client.js
// Vanilla JavaScript version - no Odoo module dependencies

(function() {
    'use strict';

    // WhatsApp Chat Client Class
    class WhatsAppChatClient {
        constructor() {
            this.currentSelectedPartnerId = null;
            this.currentSelectedContactName = null;
            this.autoRefreshInterval = null;
            this.lastMessageId = 0;
            this.isInitialized = false;
            this.isSending = false; // Add this line
            this.boundHandleSendClick = null; // Add this line
            this.eventListeners = [];
        }

        addEventListener(element, event, handler) {
            console.log(`Adding event listener: ${event} to`, element);
            if (!element || !event || !handler) {
                console.error('Invalid arguments for addEventListener', {element, event, handler});
                return;
            }
            
            element.addEventListener(event, handler);
            this.eventListeners.push({ element, event, handler });
            console.log(`Listener added. Total listeners: ${this.eventListeners.length}`);
        }

        // Helper function to get CSRF token
        getCSRFToken() {
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
                            document.querySelector('input[name="csrf_token"]')?.value ||
                            window.odoo?.csrf_token;
            return csrfToken;
        }

        // Enhanced field finder - works with Odoo's field rendering
        findOdooField(fieldName) {
            // Try multiple selectors that Odoo might use
            const selectors = [
                `input[name="${fieldName}"]`,
                `[name="${fieldName}"]`,
                `input[data-field-name="${fieldName}"]`,
                `[data-field-name="${fieldName}"]`,
                `.o_field_widget[name="${fieldName}"] input`,
                `.o_field_widget[name="${fieldName}"] textarea`,
                `#${fieldName}`,
                `.o_field_${fieldName} input`
            ];

            for (const selector of selectors) {
                const element = document.querySelector(selector);
                if (element) {
                    console.log(`Found field ${fieldName} using selector: ${selector}`);
                    return element;
                }
            }
            
            console.warn(`Field ${fieldName} not found with any selector`);
            return null;
        }
        

        // Helper function to make RPC calls using fetch
        async makeRpcCall(model, method, args = [], kwargs = {}) {
            const params = {
                jsonrpc: "2.0",
                method: "call",
                params: {
                    model: model,
                    method: method,
                    args: args,
                    kwargs: kwargs
                },
                id: Math.floor(Math.random() * 1000000)
            };

            const response = await fetch('/web/dataset/call_kw', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken(),
                },
                body: JSON.stringify(params)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (data.error) {
                console.error('RPC Error Details:', data.error);
                throw new Error(data.error.data?.message || data.error.message || 'RPC Error');
            }

            return data.result;
        }

        // Function to render messages HTML dynamically
        renderMessages(messagesHtml) {
            const messagesContainer = document.getElementById('chat-messages-container');
            if (messagesContainer) {
                messagesContainer.innerHTML = messagesHtml;
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            } else {
                console.warn("Messages container not found!");
            }
        }

        // Enhanced function to update Odoo fields
        updateOdooFields(partnerId, contactName) {
            console.log(`Updating Odoo fields: ${contactName} (ID: ${partnerId})`);
            
            // Find and update contact field - handle both regular and Odoo widget fields
            const contactField = this.findOdooField('contact');
            if (contactField) {
                contactField.value = contactName;
                // For Odoo widgets, we need to trigger their change handlers
                const inputEvent = new Event('input', { bubbles: true });
                const changeEvent = new Event('change', { bubbles: true });
                contactField.dispatchEvent(inputEvent);
                contactField.dispatchEvent(changeEvent);
                
                // Special handling for Odoo's field widgets
                if (contactField.classList.contains('o_input')) {
                    const odooField = contactField.closest('.o_field_widget');
                    if (odooField) {
                        odooField.dispatchEvent(new CustomEvent('value_changed', {
                            detail: { value: contactName }
                        }));
                    }
                }
            }
        
            // Find and update partner ID field - handle both regular input and Odoo widget
            const partnerIdField = this.findOdooField('contact_partner_id');
            if (partnerIdField) {
                partnerIdField.value = partnerId;
                const inputEvent = new Event('input', { bubbles: true });
                const changeEvent = new Event('change', { bubbles: true });
                partnerIdField.dispatchEvent(inputEvent);
                partnerIdField.dispatchEvent(changeEvent);
                
                // Special handling for Odoo's field widgets
                if (partnerIdField.classList.contains('o_input')) {
                    const odooField = partnerIdField.closest('.o_field_widget');
                    if (odooField) {
                        odooField.dispatchEvent(new CustomEvent('value_changed', {
                            detail: { value: partnerId }
                        }));
                    }
                }
            }
        
            // Force Odoo to recognize the field changes
            setTimeout(() => {
                const formView = document.querySelector('.o_form_view');
                if (formView) {
                    formView.dispatchEvent(new CustomEvent('field_changed', {
                        detail: {
                            fieldName: 'contact_partner_id',
                            value: partnerId
                        }
                    }));
                    formView.dispatchEvent(new CustomEvent('field_changed', {
                        detail: {
                            fieldName: 'contact',
                            value: contactName
                        }
                    }));
                }
            }, 100);
        }

        // Function to handle contact selection (client-side)
        async selectContact(partnerId, contactName) {
            try {
                // Validate and parse input
                partnerId = parseInt(partnerId);
                if (isNaN(partnerId)) {
                    console.error('Invalid partner ID:', partnerId);
                    return;
                }
        
                // Update client state
                this.currentSelectedPartnerId = partnerId;
                this.currentSelectedContactName = contactName || `Contact ${partnerId}`;
                this.lastMessageId = 0;
        
                // Update UI immediately
                this.updateContactSelectionUI(partnerId);
                this.updateChatHeader(this.currentSelectedContactName);
        
                // Synchronize with Odoo form fields
                await this.updateOdooFields(partnerId, this.currentSelectedContactName);
        
                // Load messages for this contact
                const messagesHtml = await this.makeRpcCall(
                    'whatsapp.chat',
                    'rpc_get_messages_html',
                    [partnerId]
                );
                this.renderMessages(messagesHtml);
        
            } catch (error) {
                console.error("Error in selectContact:", error);
                // Show error to user
                this.renderMessages(`
                    <div class="chat-error">
                        Failed to load conversation: ${error.message}
                    </div>
                `);
            }
        }

        updateChatHeader(contactName) {
            const chatHeader = document.getElementById('chat-header-contact-name');
            if (chatHeader) {
                chatHeader.textContent = contactName;
            } else {
                console.warn('Chat header element not found');
            }
        }

        // Enhanced function to get message text
        getMessageText() {
            // Try multiple ways to find the message input
            const messageInput = document.querySelector('textarea[name="new_message"]') ||
                               document.querySelector('.o_whatsapp_new_message textarea') ||
                               document.querySelector('.o_whatsapp_new_message') ||
                               this.findOdooField('new_message');
            
            if (messageInput) {
                console.log('Found message input:', messageInput, 'Value:', messageInput.value);
                return messageInput.value ? messageInput.value.trim() : '';
            }
            
            console.error('Message input not found. Selectors tried:', [
                'textarea[name="new_message"]',
                '.o_whatsapp_new_message textarea',
                '.o_whatsapp_new_message',
                'Odoo field new_message'
            ]);
            return '';
        }

        // Function to send message via RPC
        async sendMessage(recordId) {
            const messageText = this.getMessageText();

            console.log('Send message attempt:', {
                currentSelectedPartnerId: this.currentSelectedPartnerId,
                messageText: messageText,
                recordId: recordId
            });

            if (!this.currentSelectedPartnerId) {
                console.error("No contact selected!");
                alert("Please select a contact first.");
                return;
            }

            if (!messageText) {
                console.warn("Message is empty.");
                // Show user-friendly message
                const messagesContainer = document.getElementById('chat-messages-container');
                if (messagesContainer) {
                    const tempMsg = document.createElement('div');
                    tempMsg.style.cssText = 'color: orange; padding: 10px; text-align: center; font-style: italic;';
                    tempMsg.textContent = 'Please enter a message';
                    messagesContainer.appendChild(tempMsg);
                    setTimeout(() => tempMsg.remove(), 3000);
                }
                return;
            }

            // Show sending indicator
            const sendButton = document.querySelector('.o_whatsapp_send_button');
            const originalButtonText = sendButton ? sendButton.textContent : '';
            if (sendButton) {
                sendButton.textContent = 'Sending...';
                sendButton.disabled = true;
            }

            try {
                await this.makeRpcCall(
                    'whatsapp.chat',
                    'send_message',
                    [recordId],
                    {
                        new_message: messageText,
                        contact_partner_id: this.currentSelectedPartnerId,
                    }
                );

                // Clear the input field immediately
                const messageInput = this.findOdooField('new_message') || 
                                   document.querySelector('textarea[name="new_message"]') ||
                                   document.querySelector('.o_whatsapp_new_message textarea') ||
                                   document.querySelector('.o_whatsapp_new_message');
                
                if (messageInput) {
                    messageInput.value = '';
                    // Trigger change event in case Odoo needs to sync the field
                    messageInput.dispatchEvent(new Event('change', { bubbles: true }));
                    messageInput.dispatchEvent(new Event('input', { bubbles: true }));
                }

                // After sending, immediately refresh the chat area for the current contact
                await this.selectContact(this.currentSelectedPartnerId, this.currentSelectedContactName);

                // Optionally, refresh contacts list as well
                await this.updateContactsList();

            } catch (error) {
                console.error("Error sending message via RPC:", error);
                // Show user-friendly error message
                const messagesContainer = document.getElementById('chat-messages-container');
                if (messagesContainer) {
                    const errorMsg = document.createElement('div');
                    errorMsg.style.cssText = 'color: red; padding: 10px; text-align: center; background: #ffebee; border-radius: 4px; margin: 10px;';
                    errorMsg.textContent = `Failed to send message: ${error.message || 'Unknown error'}`;
                    messagesContainer.appendChild(errorMsg);
                    setTimeout(() => errorMsg.remove(), 5000);
                }
            } finally {
                // Restore button state
                if (sendButton) {
                    sendButton.textContent = originalButtonText;
                    sendButton.disabled = false;
                }
            }
        }

        // Function to update the contacts list (left panel)
        async updateContactsList() {
            console.log("Updating contacts list...");
            try {
                const contactsHtml = await this.makeRpcCall(
                    'whatsapp.chat',
                    'rpc_get_contacts_html',
                    [],
                    {}
                );
                
                const contactsContainer = document.querySelector('.chat-contacts .contacts-list') ||
                                        document.querySelector('.o_whatsapp_contacts_html');
                if (contactsContainer) {
                    contactsContainer.innerHTML = contactsHtml;
                    // Re-attach click listeners to new contact items
                    this.attachContactClickListeners();
                    // Re-apply selection highlight after list update
                    if (this.currentSelectedPartnerId) {
                        const selectedItem = document.querySelector(`.contact-item[data-partner-id="${this.currentSelectedPartnerId}"]`);
                        if (selectedItem) {
                            selectedItem.style.backgroundColor = '#e8f5e8';
                            selectedItem.style.border = '2px solid #25D366';
                            selectedItem.classList.add('selected');
                        }
                    }
                }
            } catch (error) {
                console.error("Error updating contacts list:", error);
            }
        }

        // Auto-refresh functionality for the chat and contacts
        startAutoRefresh() {
            if (this.autoRefreshInterval) {
                clearInterval(this.autoRefreshInterval);
            }
            this.autoRefreshInterval = setInterval(async () => {
                if (document.visibilityState === 'visible') { 
                    if (this.currentSelectedPartnerId) {
                        await this.selectContact(this.currentSelectedPartnerId, this.currentSelectedContactName);
                    }
                    await this.updateContactsList();
                }
            }, 10000); // 10 seconds
        }

        // Function to attach click listeners to contact items
        attachContactClickListeners() {
            console.log('Attaching contact click listeners...');
            
            // Use event delegation for better reliability
            document.addEventListener('click', (event) => {
                const contactItem = event.target.closest('.contact-item');
                if (!contactItem) return;
                
                event.preventDefault();
                event.stopPropagation();
                
                // Get data attributes with fallbacks
                const partnerId = contactItem.dataset.partnerId || 
                                 contactItem.getAttribute('data-partner-id');
                const contactName = contactItem.dataset.contactName || 
                                  contactItem.getAttribute('data-contact-name') ||
                                  contactItem.querySelector('strong')?.textContent.trim() || 
                                  `Contact ${partnerId}`;
                
                if (partnerId && !isNaN(parseInt(partnerId))) {
                    this.selectContact(parseInt(partnerId), contactName);
                } else {
                    console.error('Invalid contact data:', { partnerId, contactName });
                }
            });
        }

        // Enhanced message input handling
        setupMessageInput() {
            // Find the message input
            const messageInput = this.findOdooField('new_message') || 
                                document.querySelector('textarea[name="new_message"]') ||
                                document.querySelector('.o_whatsapp_new_message textarea') ||
                                document.querySelector('.o_whatsapp_new_message');
            
            if (messageInput) {
                // Clone to remove existing listeners
                const newMessageInput = messageInput.cloneNode(true);
                messageInput.parentNode.replaceChild(newMessageInput, messageInput);
                
                // Add managed listeners
                this.addEventListener(newMessageInput, 'keydown', (event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        event.stopPropagation();
                        this.handleSendMessage();
                    }
                });
        
                this.addEventListener(newMessageInput, 'input', () => {
                    newMessageInput.style.height = 'auto';
                    newMessageInput.style.height = newMessageInput.scrollHeight + 'px';
                });
        
                this.addEventListener(newMessageInput, 'keypress', (event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        event.stopPropagation();
                        return false;
                    }
                });
            } else {
                console.error('Message input not found during setup!');
            }
        }

        // Handle send message with better error handling and UX
        async handleSendMessage() {

            if (this.lastSendAttempt && (Date.now() - this.lastSendAttempt < 1000)) {
                console.log('Send message throttled');
                return;
            }
            this.lastSendAttempt = Date.now();


            // Check if already sending
            if (this.isSending) {
                console.log('Message sending already in progress');
                return;
            }
            
            this.isSending = true;
            
            try {
                // Get the message text directly from the input field
                const messageInput = document.querySelector('textarea[name="new_message"]') ||
                                document.querySelector('.o_whatsapp_new_message textarea') ||
                                document.querySelector('.o_whatsapp_new_message') ||
                                this.findOdooField('new_message');
                
                if (!messageInput) {
                    console.error("Message input element not found!");
                    return;
                }

                const messageText = messageInput.value.trim();
                
                if (!this.currentSelectedPartnerId) {
                    this.showChatError('Please select a contact first');
                    return;
                }

                if (!messageText) {
                    this.showChatError('Please enter a message');
                    return;
                }

                this.showSendingStatus(true);

                // Call the dedicated RPC method
                const result = await this.makeRpcCall(
                    'whatsapp.chat',
                    'rpc_send_message',
                    [parseInt(this.currentSelectedPartnerId), messageText]
                );

                // Clear the input on success
                messageInput.value = '';
                messageInput.dispatchEvent(new Event('change', { bubbles: true }));
                messageInput.dispatchEvent(new Event('input', { bubbles: true }));

                // Refresh the chat
                await this.selectContact(this.currentSelectedPartnerId, this.currentSelectedContactName);

                // Show success message
                if (result && result.status === 'success') {
                    this.showChatSuccess(result.message);
                }

            } catch (error) {
                console.error("Error sending message:", error);
                this.showChatError(error.message || 'Failed to send message');
            } finally {
                this.showSendingStatus(false);
                this.isSending = false;
            }
        }


        showChatSuccess(message) {
            const messagesContainer = document.getElementById('chat-messages-container');
            if (messagesContainer) {
                const successDiv = document.createElement('div');
                successDiv.className = 'chat-success-message';
                successDiv.textContent = message;
                messagesContainer.appendChild(successDiv);
                setTimeout(() => successDiv.remove(), 3000);
            }
        }
        
        showChatError(message) {
            const messagesContainer = document.getElementById('chat-messages-container');
            if (messagesContainer) {
                const errorDiv = document.createElement('div');
                errorDiv.className = 'chat-error-message';
                errorDiv.textContent = message;
                messagesContainer.appendChild(errorDiv);
                setTimeout(() => errorDiv.remove(), 3000);
            }
        }
        
        showSendingStatus(isSending) {
            const sendButton = document.querySelector('.o_whatsapp_send_button');
            if (sendButton) {
                if (isSending) {
                    sendButton.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Sending...';
                    sendButton.disabled = true;
                } else {
                    sendButton.innerHTML = '<i class="fa fa-paper-plane"></i> Send';
                    sendButton.disabled = false;
                }
            }
        }



        updateContactSelectionUI(partnerId) {
            // Remove selection from all contacts first
            document.querySelectorAll('.contact-item').forEach(item => {
                item.style.backgroundColor = 'white';
                item.style.border = '1px solid #eee';
                item.classList.remove('selected');
            });
            
            // Highlight the selected contact
            const selectedItem = document.querySelector(`.contact-item[data-partner-id="${partnerId}"]`);
            if (selectedItem) {
                selectedItem.style.backgroundColor = '#e8f5e8';
                selectedItem.style.border = '2px solid #25D366';
                selectedItem.classList.add('selected');
                
                // Scroll the selected item into view if needed
                selectedItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            } else {
                console.warn(`Contact item with ID ${partnerId} not found in DOM`);
            }
        }

     
        // Wait for Odoo to fully render the form
        async waitForOdooForm(maxWait = 10000) {
            const startTime = Date.now();
            
            while (Date.now() - startTime < maxWait) {
                // Check if essential elements exist
                const formView = document.querySelector('.o_form_view');
                const contactField = this.findOdooField('contact_partner_id');
                
                if (formView && contactField) {
                    console.log('Odoo form is ready');
                    return true;
                }
                
                // Wait a bit before checking again
                await new Promise(resolve => setTimeout(resolve, 100));
            }
            
            console.warn('Timeout waiting for Odoo form to be ready');
            return false;
        }

        // Main initialization function
        async initialize() {

            // Verify all required methods exist
              const requiredMethods = [
                  'updateContactSelectionUI',
                  'updateChatHeader',
                  'updateOdooFields',
                  'renderMessages'
              ];
              
              requiredMethods.forEach(method => {
                  if (typeof this[method] !== 'function') {
                      console.error(`Missing required method: ${method}`);
                      throw new Error(`WhatsAppChatClient missing required method: ${method}`);
                  }
              });


          if (this.isInitialized) {
              console.log('WhatsApp Chat Client already initialized, skipping...');
              return;
          }
      
          console.log("WhatsApp Chat Client JS Initializing...");
      
          // Wait for Odoo form to be fully ready
          await this.waitForOdooForm();
      
          // Get initial selected contact from hidden fields if already set by Python
          const initialPartnerIdField = this.findOdooField('contact_partner_id');
          const initialContactNameField = this.findOdooField('contact');
      
          if (initialPartnerIdField && initialPartnerIdField.value) {
              this.currentSelectedPartnerId = parseInt(initialPartnerIdField.value);
              this.currentSelectedContactName = initialContactNameField ? initialContactNameField.value : '';
              console.log('Found initial selection:', {
                  partnerId: this.currentSelectedPartnerId,
                  contactName: this.currentSelectedContactName
              });
              
              // Ensure our client state matches Odoo's state
              await this.selectContact(this.currentSelectedPartnerId, this.currentSelectedContactName);
          } else {
              // If no initial selection, try to get from URL params
              const urlParams = new URLSearchParams(window.location.search);
              const partnerId = urlParams.get('partner_id');
              if (partnerId) {
                  const partnerName = urlParams.get('partner_name') || `Contact ${partnerId}`;
                  await this.selectContact(parseInt(partnerId), partnerName);
              }
          }
      
          // Setup message input handling
          this.setupMessageInput();
      
          // Attach event listener for sending messages
          this.addEventListener(document, 'click', (event) => {
            if (event.target.matches('.o_whatsapp_send_button') || 
                event.target.closest('.o_whatsapp_send_button')) {
                event.preventDefault();
                event.stopPropagation();
                this.handleSendMessage();
            }
        });
      
          // Attach click listeners to all contact items
          this.attachContactClickListeners();
      
          // Start auto-refresh
          this.startAutoRefresh();
      
          // Ensure proper scrolling on initial load
          setTimeout(() => {
              const messagesContainer = document.getElementById('chat-messages-container');
              if (messagesContainer) {
                  messagesContainer.scrollTop = messagesContainer.scrollHeight;
              }
          }, 300);
      
          // Add mutation observer to watch for Odoo form changes
          const formObserver = new MutationObserver((mutations) => {
              mutations.forEach((mutation) => {
                  if (mutation.type === 'attributes' && 
                      (mutation.attributeName === 'value' || mutation.attributeName === 'class')) {
                      const target = mutation.target;
                      if (target.name === 'contact_partner_id' && target.value && 
                          target.value !== this.currentSelectedPartnerId) {
                          this.selectContact(parseInt(target.value), this.currentSelectedContactName);
                      }
                  }
              });
          });
      
          const formElement = document.querySelector('.o_form_view');
          if (formElement) {
              formObserver.observe(formElement, {
                  attributes: true,
                  subtree: true,
                  attributeFilter: ['value', 'class']
              });
          }
      
          this.isInitialized = true;
          console.log("WhatsApp Chat Client initialized successfully");
      }

        // Separate click handler method
        handleSendClick(event) {
            if (event.target.matches('.o_whatsapp_send_button') || 
                event.target.closest('.o_whatsapp_send_button')) {
                event.preventDefault();
                event.stopPropagation();
                this.handleSendMessage();
            }
        }



        async updateOdooFields(partnerId, contactName) {
            console.log('Updating Odoo fields with:', { partnerId, contactName });
            
            // Find fields using multiple possible selectors
            const contactField = this.findOdooField('contact');
            const partnerIdField = this.findOdooField('contact_partner_id');
            
            if (contactField) {
                contactField.value = contactName;
                // Trigger all possible change events
                contactField.dispatchEvent(new Event('change', { bubbles: true }));
                contactField.dispatchEvent(new Event('input', { bubbles: true }));
                contactField.dispatchEvent(new Event('blur', { bubbles: true }));
            }
            
            if (partnerIdField) {
                partnerIdField.value = partnerId;
                // Trigger all possible change events
                partnerIdField.dispatchEvent(new Event('change', { bubbles: true }));
                partnerIdField.dispatchEvent(new Event('input', { bubbles: true }));
                partnerIdField.dispatchEvent(new Event('blur', { bubbles: true }));
            }
            
            // Special handling for Odoo widgets
            if (window.odoo && window.odoo.__WOWL_DEBUG__) {
                setTimeout(() => {
                    const form = document.querySelector('.o_form_view');
                    if (form) {
                        form.dispatchEvent(new CustomEvent('field_changed', {
                            detail: {
                                fieldName: 'contact_partner_id',
                                value: partnerId
                            }
                        }));
                    }
                }, 100);
            }
            
            // Wait for Odoo to process changes
            await new Promise(resolve => setTimeout(resolve, 50));
        }

        // Helper function to get current record ID
        getCurrentRecordId() {
            // Method 1: From URL hash
            let recordIdMatch = window.location.hash.match(/id=(\d+)/);
            if (recordIdMatch) {
                return parseInt(recordIdMatch[1]);
            }
            
            // Method 2: From URL pathname
            recordIdMatch = window.location.pathname.match(/\/(\d+)(?:\/|$)/);
            if (recordIdMatch) {
                return parseInt(recordIdMatch[1]);
            }
            
            // Method 3: From a hidden field or data attribute
            const recordIdField = document.querySelector('input[name="id"]');
            if (recordIdField && recordIdField.value) {
                return parseInt(recordIdField.value);
            }

            // Method 4: From URL search params
            const urlParams = new URLSearchParams(window.location.search);
            const idParam = urlParams.get('id');
            if (idParam) {
                return parseInt(idParam);
            }

            // Method 5: Try to get from Odoo's context
            if (window.odoo && window.odoo.session && window.odoo.session.active_id) {
                return parseInt(window.odoo.session.active_id);
            }

            return null;
        }

        // Cleanup function
        destroy() {
            if (this.autoRefreshInterval) {
                clearInterval(this.autoRefreshInterval);
                this.autoRefreshInterval = null;
            }
            
            // Remove all registered event listeners
            this.eventListeners.forEach(({ element, event, handler }) => {
                element.removeEventListener(event, handler);
            });
            this.eventListeners = [];
            
            this.isInitialized = false;
        }
    }



    // Global instance
    let whatsappChatClient = null;

    // Replace your current initialization code with this:
    let initializationStarted = false;

    function initializeWhatsAppChat() {
        if (initializationStarted) return;
        initializationStarted = true;
        
        console.log('Initialize WhatsApp Chat called');
        
        // Avoid multiple initializations
        if (whatsappChatClient && whatsappChatClient.isInitialized) {
            console.log('Chat client already initialized, skipping...');
            return;
        }
        
        if (whatsappChatClient) {
            whatsappChatClient.destroy();
        }
        
        whatsappChatClient = new WhatsAppChatClient();
        whatsappChatClient.initialize().catch(error => {
            console.error("Failed to initialize WhatsApp Chat:", error);
            initializationStarted = false; // Allow retry on failure
        });
    }

    // Initialize only once when DOM is ready
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(initializeWhatsAppChat, 100); // Small delay to ensure Odoo is ready
    });

    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        if (whatsappChatClient) {
            whatsappChatClient.destroy();
        }
    });

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeWhatsAppChat);
    } else {
        // DOM is already ready
        setTimeout(initializeWhatsAppChat, 100);
    }

    // Also try to initialize after delays for Odoo's dynamic content
    setTimeout(initializeWhatsAppChat, 1000);
    setTimeout(initializeWhatsAppChat, 3000);

    // Listen for Odoo's potential events
    document.addEventListener('DOMContentLoaded', initializeWhatsAppChat);
    
    // Listen for hash changes (Odoo navigation)
    window.addEventListener('hashchange', () => {
        setTimeout(initializeWhatsAppChat, 500);
    });

    // Expose to global scope for debugging
    window.WhatsAppChatClient = WhatsAppChatClient;
    window.initializeWhatsAppChat = initializeWhatsAppChat;
    window.whatsappChatClient = whatsappChatClient;

})();