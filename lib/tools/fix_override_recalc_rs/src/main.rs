use anyhow::{Context, Result};
use clap::Parser;
use futures::future::join_all;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::Duration;

#[derive(Parser, Debug)]
#[command(name = "fix-override-recalc")]
#[command(about = "Force Canvas assignment override recalculation (Rust impl)")]
struct Args {
    #[arg(long, help = "Canvas course ID")]
    course_id: u64,

    #[arg(long, help = "Canvas base URL")]
    base_url: String,

    #[arg(long, help = "Canvas API token")]
    token: String,

    #[arg(long, help = "Student user ID (mutually exclusive with group-id)")]
    student_id: Option<u64>,

    #[arg(long, help = "Group ID (mutually exclusive with student-id)")]
    group_id: Option<u64>,

    #[arg(long, help = "Dry run - don't actually touch overrides", default_value = "false")]
    dry_run: bool,

    #[arg(long, help = "Quiet mode - minimal output", default_value = "false")]
    quiet: bool,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
struct Assignment {
    id: u64,
    #[serde(default)]
    name: String,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
struct Override {
    id: u64,
    #[serde(default)]
    title: Option<String>,
    #[serde(default)]
    due_at: Option<String>,
    #[serde(default)]
    unlock_at: Option<String>,
    #[serde(default)]
    lock_at: Option<String>,
    #[serde(default)]
    student_ids: Option<Vec<u64>>,
    #[serde(default)]
    group_id: Option<u64>,
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
            .user_agent("canvas-toolbox-rust/0.1.0")
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
    ) -> Result<Vec<T>> {
        let mut all_items = Vec::new();
        let mut page = 1;

        loop {
            let url = format!("{}/api/v1/{}", self.base_url, endpoint);
            let response = self
                .client
                .get(&url)
                .bearer_auth(&self.token)
                .query(&[("per_page", "100"), ("page", &page.to_string())])
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

    async fn get_assignments(&self, course_id: u64) -> Result<Vec<Assignment>> {
        self.get_paginated(&format!("courses/{}/assignments", course_id))
            .await
    }

    async fn get_overrides(&self, course_id: u64, assignment_id: u64) -> Result<Vec<Override>> {
        self.get_paginated(&format!(
            "courses/{}/assignments/{}/overrides",
            course_id, assignment_id
        ))
        .await
    }

    async fn touch_override(
        &self,
        course_id: u64,
        assignment_id: u64,
        override_data: &Override,
    ) -> Result<()> {
        let url = format!(
            "{}/api/v1/courses/{}/assignments/{}/overrides/{}",
            self.base_url, course_id, assignment_id, override_data.id
        );

        let mut form = HashMap::new();

        // Preserve all existing values
        if let Some(due_at) = &override_data.due_at {
            form.insert("assignment_override[due_at]".to_string(), due_at.clone());
        }
        if let Some(unlock_at) = &override_data.unlock_at {
            form.insert(
                "assignment_override[unlock_at]".to_string(),
                unlock_at.clone(),
            );
        }
        if let Some(lock_at) = &override_data.lock_at {
            form.insert("assignment_override[lock_at]".to_string(), lock_at.clone());
        }
        if let Some(title) = &override_data.title {
            form.insert("assignment_override[title]".to_string(), title.clone());
        }
        if let Some(group_id) = override_data.group_id {
            form.insert(
                "assignment_override[group_id]".to_string(),
                group_id.to_string(),
            );
        }
        if let Some(student_ids) = &override_data.student_ids {
            for sid in student_ids {
                form.insert(
                    "assignment_override[student_ids][]".to_string(),
                    sid.to_string(),
                );
            }
        }

        let response = self
            .client
            .put(&url)
            .bearer_auth(&self.token)
            .form(&form)
            .send()
            .await
            .context(format!("Failed to PUT override {}", override_data.id))?;

        if !response.status().is_success() {
            anyhow::bail!("HTTP {} for PUT override", response.status());
        }

        Ok(())
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();

    // Validate mutually exclusive args
    match (args.student_id, args.group_id) {
        (Some(_), Some(_)) => {
            anyhow::bail!("Cannot specify both --student-id and --group-id");
        }
        (None, None) => {
            anyhow::bail!("Must specify either --student-id or --group-id");
        }
        _ => {}
    }

    let client = CanvasClient::new(args.base_url, args.token);

    // Fetch all assignments concurrently (actually sequentially paginated, but much faster than Python)
    if !args.quiet {
        eprintln!("Fetching assignments...");
    }
    let assignments = client.get_assignments(args.course_id).await?;
    if !args.quiet {
        eprintln!("Found {} assignments", assignments.len());
    }

    // Fetch overrides for all assignments concurrently
    if !args.quiet {
        eprintln!("Fetching overrides (concurrent)...");
    }

    let override_tasks: Vec<_> = assignments
        .iter()
        .map(|asg| {
            let client = &client;
            let course_id = args.course_id;
            let assignment_id = asg.id;
            async move {
                let overrides = client.get_overrides(course_id, assignment_id).await?;
                Ok::<_, anyhow::Error>((assignment_id, overrides))
            }
        })
        .collect();

    let override_results = join_all(override_tasks).await;

    // Filter for target overrides
    let mut target_overrides: Vec<(u64, Override, String)> = Vec::new();

    for result in override_results {
        let (assignment_id, overrides) = result?;

        for ovr in overrides {
            let matches = if let Some(student_id) = args.student_id {
                ovr.student_ids
                    .as_ref()
                    .map(|ids| ids.contains(&student_id))
                    .unwrap_or(false)
            } else if let Some(group_id) = args.group_id {
                ovr.group_id == Some(group_id)
            } else {
                false
            };

            if matches {
                let assignment_name = assignments
                    .iter()
                    .find(|a| a.id == assignment_id)
                    .map(|a| a.name.clone())
                    .unwrap_or_else(|| format!("Assignment {}", assignment_id));
                target_overrides.push((assignment_id, ovr, assignment_name));
            }
        }
    }

    if target_overrides.is_empty() {
        println!("No overrides found to recalculate");
        return Ok(());
    }

    println!(
        "Found {} override(s) to {}",
        target_overrides.len(),
        if args.dry_run { "preview" } else { "touch" }
    );

    // Touch overrides (concurrently if not dry-run)
    if args.dry_run {
        for (assignment_id, ovr, name) in target_overrides {
            println!(
                "  [DRY] Assignment {} ({}): override {}",
                assignment_id,
                name.chars().take(40).collect::<String>(),
                ovr.id
            );
        }
    } else {
        let touch_tasks: Vec<_> = target_overrides
            .iter()
            .map(|(assignment_id, ovr, name)| {
                let client = &client;
                let course_id = args.course_id;
                let assignment_id = *assignment_id;
                let ovr = ovr.clone();
                let name = name.clone();
                async move {
                    client.touch_override(course_id, assignment_id, &ovr).await?;
                    Ok::<_, anyhow::Error>((assignment_id, ovr.id, name))
                }
            })
            .collect();

        let touch_results = join_all(touch_tasks).await;

        let mut success_count = 0;
        let mut fail_count = 0;

        for result in touch_results {
            match result {
                Ok((assignment_id, override_id, name)) => {
                    success_count += 1;
                    if !args.quiet {
                        println!(
                            "  [OK] Assignment {} ({}): override {} recalculated",
                            assignment_id,
                            name.chars().take(40).collect::<String>(),
                            override_id
                        );
                    }
                }
                Err(e) => {
                    fail_count += 1;
                    eprintln!("  [FAIL] {}", e);
                }
            }
        }

        println!(
            "\n✓ Recalculated {} override(s) successfully",
            success_count
        );
        if fail_count > 0 {
            eprintln!("✗ {} operation(s) failed", fail_count);
            std::process::exit(1);
        }
    }

    Ok(())
}
