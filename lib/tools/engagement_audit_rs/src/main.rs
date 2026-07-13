use anyhow::{Context, Result};
use clap::Parser;
use futures::future::join_all;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::time::Duration;

#[derive(Parser, Debug)]
#[command(name = "engagement-audit")]
#[command(about = "Fetch Canvas engagement data for Title IV audit (Rust impl)")]
struct Args {
    #[arg(long, help = "Canvas course ID")]
    course_id: u64,

    #[arg(long, help = "Canvas base URL")]
    base_url: String,

    #[arg(long, help = "Canvas API token")]
    token: String,

    #[arg(long, help = "Comma-separated user IDs to fetch")]
    user_ids: String,

    #[arg(long, help = "Quiet mode - minimal output", default_value = "false")]
    quiet: bool,
}

#[derive(Debug, Serialize)]
struct StudentEngagement {
    user_id: u64,
    submission_timestamps: Vec<String>,
    discussion_timestamps: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct Submission {
    #[serde(default)]
    submitted_at: Option<String>,
}

#[derive(Debug, Deserialize)]
struct DiscussionTopic {
    id: u64,
}

#[derive(Debug, Deserialize)]
struct DiscussionEntry {
    #[serde(default)]
    user_id: Option<u64>,
    #[serde(default)]
    created_at: Option<String>,
    #[serde(default)]
    updated_at: Option<String>,
}

struct CanvasClient {
    client: Client,
    base_url: String,
    token: String,
}

impl CanvasClient {
    fn new(base_url: String, token: String) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .user_agent("canvas-toolbox-rust/1.5.2")
            .build()
            .expect("Failed to build HTTP client");

        Self {
            client,
            base_url,
            token,
        }
    }

    async fn get_paginated<T: for<'de> Deserialize<'de>>(
        &self,
        endpoint: &str,
        params: &[(&str, String)],
    ) -> Result<Vec<T>> {
        let mut all_items = Vec::new();
        let mut page = 1;

        loop {
            let url = format!("{}/api/v1/{}", self.base_url, endpoint);

            let mut query_params: Vec<(&str, String)> = params.to_vec();
            query_params.push(("per_page", "100".to_string()));
            query_params.push(("page", page.to_string()));

            let response = self
                .client
                .get(&url)
                .bearer_auth(&self.token)
                .query(&query_params)
                .send()
                .await
                .context(format!("Failed to GET {}", endpoint))?;

            if !response.status().is_success() {
                anyhow::bail!("HTTP {} for {}", response.status(), endpoint);
            }

            let items: Vec<T> = response
                .json()
                .await
                .context(format!("Failed to parse JSON from {}", endpoint))?;

            if items.is_empty() {
                break;
            }

            all_items.extend(items);
            page += 1;
        }

        Ok(all_items)
    }

    async fn fetch_student_submissions(
        &self,
        course_id: u64,
        user_id: u64,
    ) -> Result<Vec<String>> {
        let endpoint = format!("courses/{}/students/submissions", course_id);
        let params = vec![("student_ids[]", user_id.to_string())];

        let submissions: Vec<Submission> = self.get_paginated(&endpoint, &params).await?;

        let timestamps: Vec<String> = submissions
            .into_iter()
            .filter_map(|s| s.submitted_at)
            .collect();

        Ok(timestamps)
    }

    async fn fetch_discussion_topics(&self, course_id: u64) -> Result<Vec<u64>> {
        let endpoint = format!("courses/{}/discussion_topics", course_id);
        let topics: Vec<DiscussionTopic> = self.get_paginated(&endpoint, &[]).await?;
        Ok(topics.into_iter().map(|t| t.id).collect())
    }

    async fn fetch_discussion_entries_for_topic(
        &self,
        course_id: u64,
        topic_id: u64,
        user_id: u64,
    ) -> Result<Vec<String>> {
        let endpoint = format!("courses/{}/discussion_topics/{}/entries", course_id, topic_id);

        // Try to fetch, but silently skip if 404 (some topics return 404)
        let result: Result<Vec<DiscussionEntry>> = self.get_paginated(&endpoint, &[]).await;

        let entries = match result {
            Ok(e) => e,
            Err(_) => return Ok(Vec::new()), // Skip on error
        };

        let mut timestamps = Vec::new();
        for entry in entries {
            if entry.user_id == Some(user_id) {
                if let Some(ts) = entry.created_at {
                    timestamps.push(ts);
                }
                if let Some(ts) = entry.updated_at {
                    timestamps.push(ts);
                }
            }
        }

        Ok(timestamps)
    }

    async fn fetch_student_engagement(
        &self,
        course_id: u64,
        user_id: u64,
        topic_ids: &[u64],
    ) -> Result<StudentEngagement> {
        // Fetch submissions for this student
        let submission_timestamps = self
            .fetch_student_submissions(course_id, user_id)
            .await
            .unwrap_or_default();

        // Fetch discussion entries for this student across all topics
        let discussion_tasks: Vec<_> = topic_ids
            .iter()
            .map(|&topic_id| {
                let client = &self;
                async move {
                    client
                        .fetch_discussion_entries_for_topic(course_id, topic_id, user_id)
                        .await
                        .unwrap_or_default()
                }
            })
            .collect();

        let discussion_results = join_all(discussion_tasks).await;
        let discussion_timestamps: Vec<String> = discussion_results
            .into_iter()
            .flat_map(|v| v)
            .collect();

        // Deduplicate timestamps
        let unique_discussion_timestamps: Vec<String> = discussion_timestamps
            .into_iter()
            .collect::<HashSet<_>>()
            .into_iter()
            .collect();

        Ok(StudentEngagement {
            user_id,
            submission_timestamps,
            discussion_timestamps: unique_discussion_timestamps,
        })
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();

    // Parse user IDs from comma-separated string
    let user_ids: Vec<u64> = args
        .user_ids
        .split(',')
        .filter_map(|s| s.trim().parse::<u64>().ok())
        .collect();

    if user_ids.is_empty() {
        anyhow::bail!("No valid user IDs provided");
    }

    let client = CanvasClient::new(args.base_url, args.token);

    if !args.quiet {
        eprintln!("Fetching discussion topics...");
    }

    // Fetch discussion topics once (shared across all students)
    let topic_ids = client
        .fetch_discussion_topics(args.course_id)
        .await
        .context("Failed to fetch discussion topics")?;

    if !args.quiet {
        eprintln!("Found {} discussion topics", topic_ids.len());
        eprintln!("Fetching engagement data for {} students (concurrent)...", user_ids.len());
    }

    // Fetch engagement data for all students concurrently
    let engagement_tasks: Vec<_> = user_ids
        .iter()
        .map(|&user_id| {
            let client_ref = &client;
            let topic_ids_ref = &topic_ids;
            async move {
                client_ref
                    .fetch_student_engagement(args.course_id, user_id, topic_ids_ref)
                    .await
            }
        })
        .collect();

    let engagement_results = join_all(engagement_tasks).await;

    // Collect successful results
    let mut engagements = Vec::new();
    let mut failed_count = 0;

    for (idx, result) in engagement_results.into_iter().enumerate() {
        match result {
            Ok(engagement) => engagements.push(engagement),
            Err(e) => {
                failed_count += 1;
                if !args.quiet {
                    eprintln!("  [WARN] Failed to fetch student {}: {}", user_ids[idx], e);
                }
            }
        }
    }

    if !args.quiet {
        eprintln!(
            "Successfully fetched {}/{} students",
            engagements.len(),
            user_ids.len()
        );
        if failed_count > 0 {
            eprintln!("  {} student(s) failed", failed_count);
        }
    }

    // Output JSON to stdout
    let json = serde_json::to_string(&engagements)
        .context("Failed to serialize engagement data")?;
    println!("{}", json);

    Ok(())
}
