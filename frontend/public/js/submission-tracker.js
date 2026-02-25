// submission-tracker.js
// JavaScript for Submission Tracker dashboard

const API_BASE_URL = window.location.origin;
let allSubmissions = [];
let currentSubmission = null;

// Check authentication on page load
document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('authToken');
    if (!token) {
        window.location.href = '/login.html';
        return;
    }

    loadSubmissions();
    setupFilters();
});

// Load submissions from API
async function loadSubmissions() {
    const token = localStorage.getItem('authToken');

    try {
        // Load submissions
        const submissionsResponse = await fetch(`${API_BASE_URL}/api/agent/submissions`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!submissionsResponse.ok) {
            if (submissionsResponse.status === 401) {
                logout();
                return;
            }
            throw new Error('Failed to load submissions');
        }

        const submissionsData = await submissionsResponse.json();
        allSubmissions = submissionsData.submissions || [];

        // Load stats
        const statsResponse = await fetch(`${API_BASE_URL}/api/agent/stats`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (statsResponse.ok) {
            const statsData = await statsResponse.json();
            displayStats(statsData.stats);
        }

        // Display submissions
        displaySubmissions(allSubmissions);

    } catch (error) {
        console.error('Error loading submissions:', error);
        document.getElementById('loading-state').innerHTML = `
            <p style="color: #ef4444;">Error loading submissions: ${error.message}</p>
        `;
    }
}

// Display statistics
function displayStats(stats) {
    document.getElementById('stat-total').textContent = stats.total || 0;
    document.getElementById('stat-pending').textContent = stats.pending || 0;
    document.getElementById('stat-submitted').textContent = stats.submitted || 0;
    document.getElementById('stat-approved').textContent = stats.approved || 0;
    document.getElementById('stat-declined').textContent = stats.declined || 0;
}

// Display submissions in table
function displaySubmissions(submissions) {
    const loadingState = document.getElementById('loading-state');
    const emptyState = document.getElementById('empty-state');
    const table = document.getElementById('submissions-table');
    const tbody = document.getElementById('submissions-body');

    loadingState.style.display = 'none';

    if (submissions.length === 0) {
        emptyState.style.display = 'block';
        table.style.display = 'none';
        return;
    }

    emptyState.style.display = 'none';
    table.style.display = 'table';

    tbody.innerHTML = submissions.map(sub => `
        <tr>
            <td>
                <span style="font-family: monospace; font-size: 12px;">${sub.applicationId.substring(0, 8)}...</span>
            </td>
            <td>
                <div style="font-weight: 500;">${sub.lenderName || 'Unknown'}</div>
                <div style="font-size: 12px; color: #6b7280; margin-top: 2px;">${formatUrl(sub.lenderUrl)}</div>
            </td>
            <td>
                <span class="status-badge ${sub.status}">${formatStatus(sub.status)}</span>
            </td>
            <td>
                <div>${formatDate(sub.submittedAt || sub.createdAt)}</div>
                <div style="font-size: 12px; color: #6b7280;">${formatTimeAgo(sub.submittedAt || sub.createdAt)}</div>
            </td>
            <td>
                ${sub.userInterventions > 0 ?
                    `<span style="color: #f59e0b;">${sub.userInterventions} time${sub.userInterventions > 1 ? 's' : ''}</span>` :
                    '<span style="color: #6b7280;">None</span>'}
            </td>
            <td>
                <div class="actions">
                    <button class="btn-small btn-view" onclick="viewSubmission('${sub.id}')">View</button>
                    <select onchange="updateStatus('${sub.id}', this.value)" style="padding: 6px; border-radius: 4px; border: 1px solid #d1d5db; font-size: 12px;">
                        <option value="">Change Status</option>
                        <option value="pending" ${sub.status === 'pending' ? 'disabled' : ''}>Pending</option>
                        <option value="submitted" ${sub.status === 'submitted' ? 'disabled' : ''}>Submitted</option>
                        <option value="approved" ${sub.status === 'approved' ? 'disabled' : ''}>Approved</option>
                        <option value="declined" ${sub.status === 'declined' ? 'disabled' : ''}>Declined</option>
                    </select>
                    <button class="btn-small btn-delete" onclick="deleteSubmission('${sub.id}')">Delete</button>
                </div>
            </td>
        </tr>
    `).join('');
}

// Setup filters
function setupFilters() {
    const statusFilter = document.getElementById('filter-status');
    const searchFilter = document.getElementById('filter-search');

    statusFilter.addEventListener('change', applyFilters);
    searchFilter.addEventListener('input', applyFilters);
}

// Apply filters
function applyFilters() {
    const statusFilter = document.getElementById('filter-status').value;
    const searchFilter = document.getElementById('filter-search').value.toLowerCase();

    let filtered = allSubmissions;

    // Filter by status
    if (statusFilter) {
        filtered = filtered.filter(sub => sub.status === statusFilter);
    }

    // Filter by search
    if (searchFilter) {
        filtered = filtered.filter(sub =>
            sub.applicationId.toLowerCase().includes(searchFilter) ||
            (sub.lenderName && sub.lenderName.toLowerCase().includes(searchFilter)) ||
            sub.lenderUrl.toLowerCase().includes(searchFilter)
        );
    }

    displaySubmissions(filtered);
}

// View submission details
async function viewSubmission(submissionId) {
    const token = localStorage.getItem('authToken');

    try {
        const response = await fetch(`${API_BASE_URL}/api/agent/submissions/${submissionId}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) throw new Error('Failed to load submission details');

        const data = await response.json();
        currentSubmission = data.submission;
        showModal(currentSubmission);

    } catch (error) {
        alert('Error loading submission details: ' + error.message);
    }
}

// Show modal with submission details
function showModal(submission) {
    const modal = document.getElementById('submission-modal');
    const modalBody = document.getElementById('modal-body');

    modalBody.innerHTML = `
        <div class="detail-group">
            <label>Submission ID</label>
            <div class="value" style="font-family: monospace;">${submission.id}</div>
        </div>
        <div class="detail-group">
            <label>Application ID</label>
            <div class="value" style="font-family: monospace;">${submission.applicationId}</div>
        </div>
        <div class="detail-group">
            <label>Lender</label>
            <div class="value">${submission.lenderName || 'Unknown'}</div>
            <div class="value" style="font-size: 12px; color: #6b7280; margin-top: 4px;">${submission.lenderUrl}</div>
        </div>
        <div class="detail-group">
            <label>Status</label>
            <div><span class="status-badge ${submission.status}">${formatStatus(submission.status)}</span></div>
        </div>
        <div class="detail-group">
            <label>Submitted At</label>
            <div class="value">${formatDate(submission.submittedAt || submission.createdAt)}</div>
        </div>
        <div class="detail-group">
            <label>User Interventions</label>
            <div class="value">${submission.userInterventions || 0}</div>
        </div>
        ${submission.errorMessage ? `
        <div class="detail-group">
            <label>Error Message</label>
            <div class="value" style="color: #ef4444;">${submission.errorMessage}</div>
        </div>
        ` : ''}
        ${submission.automationPlan ? `
        <div class="detail-group">
            <label>Automation Steps</label>
            <div class="value">${submission.automationPlan.steps ? submission.automationPlan.steps.length : 0} steps</div>
        </div>
        ` : ''}
        <div class="detail-group">
            <label>Created At</label>
            <div class="value">${formatDate(submission.createdAt)}</div>
        </div>
        <div class="detail-group">
            <label>Last Updated</label>
            <div class="value">${formatDate(submission.updatedAt)}</div>
        </div>
    `;

    modal.classList.add('active');
}

// Close modal
function closeModal() {
    document.getElementById('submission-modal').classList.remove('active');
}

// Update submission status
async function updateStatus(submissionId, newStatus) {
    if (!newStatus) return;

    const token = localStorage.getItem('authToken');

    if (!confirm(`Are you sure you want to change the status to "${formatStatus(newStatus)}"?`)) {
        // Reset the dropdown
        event.target.value = '';
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/agent/submissions/${submissionId}`, {
            method: 'PATCH',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ status: newStatus })
        });

        if (!response.ok) throw new Error('Failed to update status');

        // Reload submissions
        loadSubmissions();

    } catch (error) {
        alert('Error updating status: ' + error.message);
    }
}

// Delete submission
async function deleteSubmission(submissionId) {
    if (!confirm('Are you sure you want to delete this submission? This cannot be undone.')) {
        return;
    }

    const token = localStorage.getItem('authToken');

    try {
        const response = await fetch(`${API_BASE_URL}/api/agent/submissions/${submissionId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) throw new Error('Failed to delete submission');

        // Reload submissions
        loadSubmissions();

    } catch (error) {
        alert('Error deleting submission: ' + error.message);
    }
}

// Logout function
function logout() {
    localStorage.removeItem('authToken');
    localStorage.removeItem('user');
    window.location.href = '/login.html';
}

// Utility functions
function formatStatus(status) {
    return status.charAt(0).toUpperCase() + status.slice(1);
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatTimeAgo(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
}

function formatUrl(url) {
    try {
        const urlObj = new URL(url);
        return urlObj.hostname;
    } catch {
        return url;
    }
}

// Close modal when clicking outside
document.getElementById('submission-modal').addEventListener('click', (e) => {
    if (e.target.id === 'submission-modal') {
        closeModal();
    }
});
