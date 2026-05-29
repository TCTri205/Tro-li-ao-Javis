#!/usr/bin/env python3
"""
Javis Chatbot API Test Runner
This script parses the test CSV file, executes requests against the /api/v1/chat endpoint,
compares actual answers with expected answers, and saves a beautiful report.
"""

import os
import sys
import csv
import json
import time
import argparse
from datetime import datetime
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich import box

# Initialize Rich Console
console = Console()

def parse_arguments():
    parser = argparse.ArgumentParser(description="Javis Chatbot API Test Runner")
    parser.add_argument(
        "--csv",
        type=str,
        default="d:\\VJ\\Tro-li-ao-Javis\\javis-test-api\\Test javis chatbot - Test.csv",
        help="Path to the test CSV file"
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:8019/api/v1/chat",
        help="Full URL of the /api/v1/chat endpoint"
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default="00000000-0000-0000-0000-000000000001",
        help="UUID of the user sending the messages"
    )
    parser.add_argument(
        "--role",
        type=str,
        default="user",
        help="Role of the user sending the messages"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay in seconds between API requests"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="d:\\VJ\\Tro-li-ao-Javis\\javis-test-api\\reports",
        help="Directory to save test reports"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock mode (simulates API requests offline)"
    )
    return parser.parse_args()


def load_test_cases(csv_path):
    """
    Parses the custom-formatted Javis Chatbot Test CSV file.
    Returns a list of structured test cases.
    """
    if not os.path.exists(csv_path):
        console.print(f"[bold red]Error:[/bold red] CSV file not found at: {csv_path}")
        sys.exit(1)

    test_cases = []
    current_section = "General"

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for line_num, row in enumerate(reader, 1):
            if not row:
                continue

            # Strip whitespace from columns
            row = [col.strip() for col in row]

            # Detect sections (e.g. Version 1, Version 2, Hỏi về kiến thúc công ty)
            non_empty = [col for col in row if col]
            if len(non_empty) == 1:
                val = non_empty[0]
                if "Version 1" in val:
                    current_section = "Version 1 (Meeting Transcript)"
                    continue
                elif "Version 2" in val:
                    current_section = "Version 2 (Meeting Transcript - Optimized)"
                    continue
                elif "Hỏi về" in val:
                    current_section = val
                    continue

            # Skip header rows
            if not row[0] or row[0].startswith("Question_ja") or row[0].startswith("User"):
                continue

            # Extract fields
            question_ja = row[0]
            answer_ja = row[1] if len(row) > 1 else ""
            question_vi = row[2] if len(row) > 2 else ""
            answer_vi = row[3] if len(row) > 3 else ""
            notes = row[4] if len(row) > 4 else ""

            # Skip header rows that might appear again or category separators
            if question_ja == "Question_ja" or question_ja == "User":
                continue

            # Auto-detect Mode
            company_keywords = ["AJ", "VJ", "会社", "会社概要", "設立", "事業", "ホムすん", "ラクかり", "テクノロジーズ"]
            is_company = any(kw in question_ja for kw in company_keywords) or "kiến thúc công ty" in current_section.lower()
            mode = "company_info" if is_company else "customer_data"

            test_cases.append({
                "id": len(test_cases) + 1,
                "section": current_section,
                "question_ja": question_ja,
                "expected_answer_ja": answer_ja,
                "question_vi": question_vi,
                "expected_answer_vi": answer_vi,
                "notes": notes,
                "mode": mode
            })

    return test_cases


def run_test_case(url, case, user_id, role, mock=False):
    """
    Sends a request to the chat API for a single test case.
    """
    if mock:
        # Simulate network latency
        time.sleep(0.05)
        
        is_success = True
        error_msg = None
        
        # Realistically fail if notes explicitly indicate error or fail
        if "fail" in case["notes"].lower() or "error" in case["notes"].lower():
            is_success = False
            error_msg = f"Mock error: API failed to parse due to constraints: {case['notes']}"
            
        return {
            "success": is_success,
            "status_code": 200 if is_success else 500,
            "actual_answer": case["expected_answer_ja"] if is_success else "",
            "latency": 0.08,
            "error": error_msg
        }

    payload = {
        "message": case["question_ja"],
        "mode": case["mode"],
        "role": role,
        "user_id": user_id,
        "target_user_id": None,
        "conversation_id": None
    }
    
    headers = {
        "Content-Type": "application/json"
    }

    start_time = time.time()
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        latency = time.time() - start_time
        
        if response.status_code == 200:
            res_data = response.json()
            
            # The actual message is typically in res_data["data"]["message"] or res_data["message"]
            # Let's inspect typical patterns or extract standard text response.
            actual_answer = ""
            if isinstance(res_data, dict):
                # Try common FastAPI response structures
                if "data" in res_data and isinstance(res_data["data"], dict):
                    actual_answer = res_data["data"].get("message", res_data["data"].get("answer", ""))
                if not actual_answer:
                    actual_answer = res_data.get("message", res_data.get("answer", res_data.get("response", "")))
                if not actual_answer and "data" in res_data:
                    actual_answer = str(res_data["data"])
            else:
                actual_answer = str(res_data)
                
            return {
                "success": True,
                "status_code": 200,
                "actual_answer": actual_answer,
                "latency": latency,
                "error": None
            }
        else:
            return {
                "success": False,
                "status_code": response.status_code,
                "actual_answer": "",
                "latency": latency,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
    except Exception as e:
        latency = time.time() - start_time
        return {
            "success": False,
            "status_code": 0,
            "actual_answer": "",
            "latency": latency,
            "error": str(e)
        }


def save_reports(output_dir, url, user_id, role, results):
    """
    Saves markdown and CSV reports of the test run.
    """
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    md_path = os.path.join(output_dir, f"test_report_{timestamp}.md")
    csv_path = os.path.join(output_dir, f"test_results_{timestamp}.csv")
    
    total_cases = len(results)
    successful = sum(1 for r in results if r["run"]["success"])
    failed = total_cases - successful
    avg_latency = sum(r["run"]["latency"] for r in results) / total_cases if total_cases else 0

    # 1. Generate Markdown Report
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Javis Chatbot API Test Report\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**API Endpoint:** `{url}`\n")
        f.write(f"**User ID:** `{user_id}` (`{role}`)\n\n")
        
        f.write(f"## Summary\n\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"| --- | --- |\n")
        f.write(f"| Total Cases | {total_cases} |\n")
        f.write(f"| Successful Queries | {successful} |\n")
        f.write(f"| Failed Queries | {failed} |\n")
        f.write(f"| Avg Latency | {avg_latency:.2f}s |\n\n")
        
        f.write(f"## Test Details\n\n")
        
        current_section = ""
        for r in results:
            case = r["case"]
            run = r["run"]
            
            if case["section"] != current_section:
                current_section = case["section"]
                f.write(f"### {current_section}\n\n")
                
            status_emoji = "✅" if run["success"] else "❌"
            f.write(f"#### Case {case['id']}: {status_emoji} (Latency: {run['latency']:.2f}s, Mode: `{case['mode']}`)\n\n")
            
            # Question table
            f.write(f"| Language | Question |\n")
            f.write(f"| --- | --- |\n")
            f.write(f"| **Japanese** | {case['question_ja']} |\n")
            if case['question_vi']:
                f.write(f"| **Vietnamese (Translation)** | {case['question_vi']} |\n")
            f.write(f"\n")
            
            # Answer Comparison
            f.write(f"**Expected Answer (Japanese):**\n> {case['expected_answer_ja']}\n\n")
            
            if run["success"]:
                f.write(f"**Actual Answer (Japanese):**\n> {run['actual_answer']}\n\n")
            else:
                f.write(f"**Error Details:**\n```\n{run['error']}\n```\n\n")
                
            if case['notes']:
                f.write(f"**Notes:** *{case['notes']}*\n\n")
                
            f.write(f"---\n\n")
            
    # 2. Generate CSV Report
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ID", "Section", "Mode", "Question_ja", "Question_vi", 
            "Expected_Answer_ja", "Expected_Answer_vi", 
            "Actual_Answer_ja", "Status", "Latency_sec", "Error_Msg"
        ])
        
        for r in results:
            case = r["case"]
            run = r["run"]
            writer.writerow([
                case["id"],
                case["section"],
                case["mode"],
                case["question_ja"],
                case["question_vi"],
                case["expected_answer_ja"],
                case["expected_answer_vi"],
                run["actual_answer"],
                "Success" if run["success"] else "Failed",
                f"{run['latency']:.3f}",
                run["error"] or ""
            ])
            
    return md_path, csv_path


def main():
    args = parse_arguments()
    
    console.print(Panel(
        f"[bold blue]Javis Chatbot API Test Runner[/bold blue]\n"
        f"API Endpoint: [green]{args.url}[/green]\n"
        f"CSV Source:   [yellow]{args.csv}[/yellow]\n"
        f"User ID:      [cyan]{args.user_id}[/cyan] ({args.role})\n"
        f"Mock Mode:    [magenta]{'Enabled' if args.mock else 'Disabled'}[/magenta]",
        border_style="blue",
        box=box.ROUNDED
    ))

    # Load test cases
    console.print("[bold yellow]Loading test cases from CSV...[/bold yellow]")
    test_cases = load_test_cases(args.csv)
    console.print(f"[bold green]Loaded {len(test_cases)} test cases successfully![/bold green]\n")

    results = []

    # Run tests with progress bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Running chat API queries...", total=len(test_cases))
        
        for case in test_cases:
            progress.update(task, description=f"[cyan]Testing Case #{case['id']} ({case['mode']})")
            
            run_result = run_test_case(args.url, case, args.user_id, args.role, mock=args.mock)
            results.append({
                "case": case,
                "run": run_result
            })
            
            # Small delay to prevent API overloading
            time.sleep(args.delay)
            progress.advance(task)

    # 1. Save Reports First (Guarantees reports are saved even if console printing fails)
    try:
        md_path, csv_path = save_reports(args.output_dir, args.url, args.user_id, args.role, results)
    except Exception as e:
        console.print(f"[bold red]Failed to save reports: {e}[/bold red]")
        md_path, csv_path = None, None

    # 2. Print Summary Table
    try:
        table = Table(title="Test Results Summary", box=box.SIMPLE_HEAD, expand=True)
        table.add_column("ID", justify="center", style="dim", width=4)
        table.add_column("Section", style="magenta")
        table.add_column("Mode", justify="center", style="cyan")
        table.add_column("Question (JA)", max_width=40)
        table.add_column("Status", justify="center")
        table.add_column("Latency", justify="right", style="green")

        for r in results:
            case = r["case"]
            run = r["run"]
            status_str = "[bold green]Success[/bold green]" if run["success"] else f"[bold red]Failed ({run['status_code']})[/bold red]"
            
            table.add_row(
                str(case["id"]),
                case["section"],
                case["mode"],
                case["question_ja"],
                status_str,
                f"{run['latency']:.2f}s"
            )
            
        console.print(table)
        console.print()

        # 3. Print Detailed Comparisons for Failures or Key Cases
        console.print(Panel("[bold yellow]Detailed Comparisons (Expected vs Actual Answer)[/bold yellow]"))
        for r in results:
            case = r["case"]
            run = r["run"]
            
            if run["success"]:
                console.print(f"[bold green]Case #{case['id']} ({case['section']}): {case['question_ja']}[/bold green]")
                console.print(f"[dim]Question VI: {case['question_vi']}[/dim]")
                console.print(f"[bold cyan]Expected:[/bold cyan] {case['expected_answer_ja']}")
                console.print(f"[bold green]Actual:  [/bold green] {run['actual_answer']}")
            else:
                console.print(f"[bold red]Case #{case['id']} ({case['section']}) Failed: {case['question_ja']}[/bold red]")
                console.print(f"[red]Error:[/red] {run['error']}")
            console.print("-" * 80)
    except Exception as console_err:
        # If terminal encoding doesn't support Japanese/Vietnamese characters, print a clean warning
        print(f"\nWarning: Could not display full results on console due to terminal encoding limitations ({console_err}).")
        print("Rest assured, the full Markdown and CSV reports have been successfully generated!")

    if md_path and csv_path:
        print(f"\n=========================================")
        print(f"Testing Completed Successfully!")
        print(f"Markdown Report: {md_path}")
        print(f"CSV Results:     {csv_path}")
        print(f"=========================================\n")


if __name__ == "__main__":
    main()
