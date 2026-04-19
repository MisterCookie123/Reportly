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
        const report = result.report;

        document.getElementById("loading").style.display = "none";
        document.getElementById("outputSection").style.display = "block";
        document.getElementById("generateBtn").disabled = false;

        if (report.raw_output) {
            document.getElementById("overallSummary").innerText = report.raw_output;
            return;
        }

        const healthBadge = document.getElementById("healthBadge");
        healthBadge.innerText = report.business_health;
        healthBadge.className = "health-badge " + report.business_health.replace(" ", "-").toLowerCase();

        document.getElementById("overallSummary").innerText = report.overall_summary;

        const insightsList = document.getElementById("keyInsights");
        insightsList.innerHTML = "";
        report.key_insights.forEach(insight => {
            const li = document.createElement("li");
            li.innerText = insight;
            insightsList.appendChild(li);
        });

        const postsGrid = document.getElementById("postsGrid");
        postsGrid.innerHTML = "";
        report.posts.forEach(post => {
            const card = document.createElement("div");
            card.className = "post-card " + post.efficiency_rating.replace(/ /g, "-").toLowerCase();
            card.innerHTML = `
                <div class="post-header">
                    <h3>${post.post_title}</h3>
                    <span class="impact-score">Score: ${post.impact_score}</span>
                </div>
                <div class="efficiency-tag">${post.efficiency_rating}</div>
                <ul class="actions">
                    ${post.top_3_strategic_actions.map(a => `<li>${a}</li>`).join("")}
                </ul>
            `;
            postsGrid.appendChild(card);
        });

        const recList = document.getElementById("recommendations");
        recList.innerHTML = "";
        report.overall_recommendations.forEach(rec => {
            const li = document.createElement("li");
            li.innerText = rec;
            recList.appendChild(li);
        });

    } catch (error) {
        alert("Something went wrong. Try again.");
        document.getElementById("loading").style.display = "none";
        document.getElementById("generateBtn").disabled = false;
    }
}

function copyReport() {
    const summary = document.getElementById("overallSummary").innerText;
    const insights = [...document.querySelectorAll("#keyInsights li")].map(li => li.innerText).join("\n");
    const recs = [...document.querySelectorAll("#recommendations li")].map(li => li.innerText).join("\n");
    const full = `REPORTLY ANALYSIS\n\nSUMMARY\n${summary}\n\nKEY INSIGHTS\n${insights}\n\nRECOMMENDATIONS\n${recs}`;
    navigator.clipboard.writeText(full);
    alert("Report copied to clipboard.");
}

function downloadPDF(type) {
    window.location.href = '/download/' + type;
}



async function logout() {
    await fetch('/auth/logout', { method: 'POST' });
    window.location.href = '/login';
}