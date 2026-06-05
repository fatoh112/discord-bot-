with open("templates/admin/members.html", "r", encoding="utf-8") as f:
    content = f.read()

modal_html = """
    <!-- Bulk Role Modal -->
    <div x-show="isBulkRoleModalOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" x-transition>
        <div @click.away="isBulkRoleModalOpen = false" class="bg-[#0f172a] border border-white/10 rounded-xl shadow-2xl w-full max-w-md overflow-hidden">
            <div class="px-6 py-4 border-b border-white/5 bg-white/[0.02]">
                <h3 class="text-lg font-bold text-white">Bulk Assign Roles</h3>
                <p class="text-sm text-muted mt-1">Modifying roles for <span class="font-semibold text-accent" x-text="selectedMembers.length"></span> selected users.</p>
            </div>
            
            <div class="p-6 space-y-4">
                <div>
                    <label class="block text-sm font-semibold text-gray-300 mb-2">Select Role</label>
                    <select x-model="selectedRole" class="w-full bg-[#0d111a] border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-accent">
                        <option value="">-- Choose a Role --</option>
                        <template x-for="role in roles" :key="role.id">
                            <option :value="role.id" x-text="role.name"></option>
                        </template>
                    </select>
                </div>
                
                <div>
                    <label class="block text-sm font-semibold text-gray-300 mb-2">Action</label>
                    <div class="flex gap-4">
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="radio" x-model="bulkRoleAction" value="add" name="role_action" class="text-accent bg-[#0d111a] border-white/10 focus:ring-accent">
                            <span class="text-sm text-gray-300">Add Role</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="radio" x-model="bulkRoleAction" value="remove" name="role_action" class="text-accent bg-[#0d111a] border-white/10 focus:ring-accent">
                            <span class="text-sm text-gray-300">Remove Role</span>
                        </label>
                    </div>
                </div>
            </div>
            
            <div class="px-6 py-4 border-t border-white/5 bg-white/[0.02] flex justify-end gap-3">
                <button @click="isBulkRoleModalOpen = false" class="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white transition-colors">Cancel</button>
                <button @click="submitBulkRole" :disabled="!selectedRole || bulkRoleLoading" class="px-4 py-2 bg-accent hover:bg-accent/90 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2">
                    <svg x-show="bulkRoleLoading" class="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                    <span x-text="bulkRoleLoading ? 'Processing...' : 'Apply Changes'"></span>
                </button>
            </div>
        </div>
    </div>
"""

# Insert modal before final </div> of content
content = content.replace("    </div>\n</div>\n{% endblock %}", modal_html + "\n    </div>\n</div>\n{% endblock %}")

state_target = """        itemsPerPage: 50,

        async init() {"""

state_replacement = """        itemsPerPage: 50,
        
        isBulkRoleModalOpen: false,
        roles: [],
        selectedRole: '',
        bulkRoleAction: 'add',
        bulkRoleLoading: false,

        async init() {"""
content = content.replace(state_target, state_replacement)


js_target = """        openBulkRoleModal() {
            this.$dispatch('notify', {msg: 'Bulk role assignment coming soon', type: 'info'});
        }"""
        
js_replacement = """        async openBulkRoleModal() {
            this.isBulkRoleModalOpen = true;
            this.selectedRole = '';
            this.bulkRoleAction = 'add';
            
            if (this.roles.length === 0) {
                try {
                    const res = await fetch(`/api/guilds/${this.selectedGuild}/roles`);
                    if (res.ok) {
                        this.roles = await res.json();
                    }
                } catch (e) {
                    console.error("Failed to fetch roles", e);
                }
            }
        },
        
        async submitBulkRole() {
            if (!this.selectedRole) return;
            this.bulkRoleLoading = true;
            
            try {
                const res = await fetch(`/api/guilds/${this.selectedGuild}/members/bulk-role`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_ids: this.selectedMembers,
                        role_id: this.selectedRole,
                        action: this.bulkRoleAction
                    })
                });
                
                const data = await res.json();
                
                if (res.ok) {
                    this.$dispatch('notify', {msg: `Successfully updated roles for ${data.processed} members`, type: 'success'});
                    this.isBulkRoleModalOpen = false;
                    this.selectedMembers = [];
                    // Refresh members to show new roles
                    this.fetchMembers();
                } else {
                    throw new Error(data.error || 'Failed to assign roles');
                }
            } catch (err) {
                console.error(err);
                this.$dispatch('notify', {msg: err.message, type: 'error'});
            } finally {
                this.bulkRoleLoading = false;
            }
        }"""
        
content = content.replace(js_target, js_replacement)

with open("templates/admin/members.html", "w", encoding="utf-8") as f:
    f.write(content)
