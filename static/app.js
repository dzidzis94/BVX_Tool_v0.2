document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const fileNameDisplay = document.getElementById('file-name-display');
    const skipConflictsCheckbox = document.getElementById('skip-conflicts-checkbox');
    const processBtn = document.getElementById('process-btn');
    const consoleOutput = document.getElementById('console-output');
    const statusBadge = document.getElementById('status-badge');
    const downloadBtn = document.getElementById('download-btn');

    let selectedFile = null;

    // Handle drag and drop events
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length > 0) {
            handleSelectedFile(files[0]);
        }
    });

    // Clicking drop zone triggers hidden file input
    dropZone.addEventListener('click', (e) => {
        if (e.target.tagName !== 'LABEL') {
            fileInput.click();
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
            handleSelectedFile(e.target.files[0]);
        }
    });

    function handleSelectedFile(file) {
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            updateStatus('error', 'Invalid File');
            consoleOutput.textContent = 'Error: Please select a valid PDF file.';
            return;
        }

        selectedFile = file;
        fileNameDisplay.textContent = `${file.name} (${formatBytes(file.size)})`;
        fileNameDisplay.classList.add('has-file');
        processBtn.disabled = false;

        // Reset output status & download button
        downloadBtn.hidden = true;
        downloadBtn.classList.add('btn-disabled');
        downloadBtn.href = '#';
        updateStatus('ready', 'Ready');
        consoleOutput.textContent = `Selected: ${file.name}\nClick "Process File" to generate .bvx.`;
    }

    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    function updateStatus(state, text) {
        statusBadge.className = 'badge';
        statusBadge.classList.add(`status-${state}`);
        statusBadge.textContent = text;
    }

    // Process button click
    processBtn.addEventListener('click', async () => {
        if (!selectedFile) return;

        processBtn.disabled = true;
        updateStatus('processing', 'Processing...');
        consoleOutput.textContent = 'Reading rows and analyzing PDF...';
        downloadBtn.hidden = true;

        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('skip_conflicts', skipConflictsCheckbox.checked ? 'true' : 'false');

        try {
            const response = await fetch('/process', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (data.report) {
                consoleOutput.textContent = data.report;
            } else if (data.error) {
                consoleOutput.textContent = data.error;
            }

            if (response.ok && data.success && data.download_url) {
                updateStatus('success', 'Success');
                downloadBtn.href = data.download_url;
                downloadBtn.hidden = false;
                downloadBtn.classList.remove('btn-disabled');
            } else {
                updateStatus('error', 'Conflict / Error');
            }
        } catch (err) {
            updateStatus('error', 'Network Error');
            consoleOutput.textContent = `Error sending request to server: ${err.message}`;
        } finally {
            processBtn.disabled = !selectedFile;
        }
    });
});
