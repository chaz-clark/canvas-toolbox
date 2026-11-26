use anyhow::{Context, Result};
use clap::Parser;
use futures::future::join_all;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::time::Duration;

#[derive(Parser, Debug)]
#[command(name = "fix-override-recalc", version)]
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

/// Tells a date the override leaves out (None) from one it sets to null
/// (Some(None)): a late grace's Until date is overridden as null, and a PUT must
/// send it back empty or Canvas puts the assignment's own Until date back (#518).
fn present<'de, D>(d: D) -> std::result::Result<Option<Option<String>>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    Option::<String>::deserialize(d).map(Some)
}

#[derive(Debug, Deserialize, Serialize, Clone)]
struct Override {
    id: u64,
    #[serde(default)]
    title: Option<String>,
    #[serde(default, deserialize_with = "present")]
    due_at: Option<Option<String>>,
    #[serde(default, deserialize_with = "present")]
    unlock_at: Option<Option<String>>,
    #[serde(default, deserialize_with = "present")]
    lock_at: Option<Option<String>>,
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
            .user_agent(concat!("canvas-toolbox-rust/", env!("CARGO_PKG_VERSION")))
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
        // Follow the Link header; never count pages. The overrides list ignores
        // ?page= and returns the same overrides every time, so waiting for an
        // empty page looped forever (#518, lesson L36).
        let mut all_items = Vec::new();
        let mut url = Some(format!("{}/api/v1/{}?per_page=100", self.base_url, endpoint));
        let mut seen = HashSet::new();

        while let Some(current) = url.take() {
            if !seen.insert(current.clone()) {
                break; // a next link back to a page already read
            }
            let response = self
                .client
                .get(&current)
                .bearer_auth(&self.token)
                .send()
                .await
                .context(format!("Failed to GET {}", endpoint))?;

            if !response.status().is_success() {
                anyhow::bail!("HTTP {} for {}", response.status(), endpoint);
            }

            url = response
                .headers()
                .get(reqwest::header::LINK)
                .and_then(|v| v.to_str().ok())
                .and_then(next_link);

            let items: Vec<T> = response
                .json()
                .await
                .context(format!("Failed to parse JSON from {}", endpoint))?;
            all_items.extend(items);
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

        let form = touch_form(override_data);

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

/// The URL of the `rel="next"` page in a Link header, if there is one.
fn next_link(header: &str) -> Option<String> {
    header.split(',').find_map(|part| {
        let mut bits = part.split(';');
        let url = bits.next()?.trim();
        let is_next = bits.any(|b| b.trim() == "rel=\"next\"");
        if is_next && url.starts_with('<') && url.ends_with('>') {
            Some(url[1..url.len() - 1].to_string())
        } else {
            None
        }
    })
}

/// Form fields that re-send an override exactly as it is (#518). Canvas's
/// docs: every overridden value must be sent again in a PUT to be kept. So
/// every date the override has goes back, a null one as an empty value, and
/// every student id goes back as its own field (one map key per id kept only
/// the last, and the PUT dropped the other students). Matches the Python
/// `_override_recalc_helper.build_touch_payload`.
fn touch_form(o: &Override) -> Vec<(String, String)> {
    let mut form = Vec::new();
    for (name, date) in [("due_at", &o.due_at), ("unlock_at", &o.unlock_at), ("lock_at", &o.lock_at)] {
        if let Some(value) = date {
            form.push((format!("assignment_override[{}]", name), value.clone().unwrap_or_default()));
        }
    }
    if let Some(title) = &o.title {
        form.push(("assignment_override[title]".to_string(), title.clone()));
    }
    if let Some(group_id) = o.group_id {
        form.push(("assignment_override[group_id]".to_string(), group_id.to_string()));
    }
    for sid in o.student_ids.iter().flatten() {
        form.push(("assignment_override[student_ids][]".to_string(), sid.to_string()));
    }
    form
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


#[cfg(test)]
mod tests {
    use super::*;

    fn parse(json: &str) -> Override {
        serde_json::from_str(json).unwrap()
    }

    #[test]
    fn next_link_is_found_or_absent() {
        let h = r#"<https://x/api/v1/a?page=2&per_page=100>; rel="next", <https://x/api/v1/a?page=1>; rel="first""#;
        assert_eq!(next_link(h).as_deref(), Some("https://x/api/v1/a?page=2&per_page=100"));
        assert_eq!(next_link(r#"<https://x/a?page=1>; rel="current""#), None);
        assert_eq!(next_link(""), None);
    }

    #[test]
    fn a_shared_override_keeps_every_student() {
        let f = touch_form(&parse(r#"{"id":1,"title":"3 students","student_ids":[100,200,300]}"#));
        let ids: Vec<_> = f.iter().filter(|(k, _)| k == "assignment_override[student_ids][]").map(|(_, v)| v.as_str()).collect();
        assert_eq!(ids, ["100", "200", "300"]);
    }

    #[test]
    fn a_null_until_date_goes_back_empty_and_an_absent_one_is_not_sent() {
        let f = touch_form(&parse(r#"{"id":1,"due_at":"2026-04-15T23:59:00Z","lock_at":null,"student_ids":[100]}"#));
        assert!(f.contains(&("assignment_override[lock_at]".to_string(), String::new())));
        assert!(f.contains(&("assignment_override[due_at]".to_string(), "2026-04-15T23:59:00Z".to_string())));
        assert!(!f.iter().any(|(k, _)| k == "assignment_override[unlock_at]"));
    }
}
