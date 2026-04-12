async function generateReport() {
    const data = document.getElementById("dataInput").value;

    if (!data.trim()) {
        alert("Please paste your data first.");
        return;
    }

    document.getElementById("loading").style.display = "block";
    document.getElementById("outputSection").style.display = "none";
    document.getElementById("generateBtn").disabled = true;

    try {
        const response = await fetch("/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ data: data })
        });

        const result = await response.json();

        document.getElementById("loading").style.display = "none";
        document.getElementById("outputSection").style.display = "block";
        document.getElementById("reportOutput").innerText = result.report;
        document.getElementById("generateBtn").disabled = false;

    } catch (error) {
        alert("Something went wrong. Try again.");
        document.getElementById("loading").style.display = "none";
        document.getElementById("generateBtn").disabled = false;
    }
}

function copyReport() {
    const report = document.getElementById("reportOutput").innerText;
    navigator.clipboard.writeText(report);
    alert("Report copied to clipboard.");
}