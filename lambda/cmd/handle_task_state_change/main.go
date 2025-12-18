package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	"lambda/models"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

// ECS Task State Change Event structures
type ECSTaskStateChangeEvent struct {
	Version    string                   `json:"version"`
	ID         string                   `json:"id"`
	DetailType string                   `json:"detail-type"`
	Source     string                   `json:"source"`
	Account    string                   `json:"account"`
	Time       string                   `json:"time"`
	Region     string                   `json:"region"`
	Resources  []string                 `json:"resources"`
	Detail     ECSTaskStateChangeDetail `json:"detail"`
}

type ECSTaskStateChangeDetail struct {
	ClusterArn         string      `json:"clusterArn"`
	TaskArn            string      `json:"taskArn"`
	TaskDefinitionArn  string      `json:"taskDefinitionArn"`
	DesiredStatus      string      `json:"desiredStatus"`
	LastStatus         string      `json:"lastStatus"`
	Containers         []Container `json:"containers"`
	StoppedReason      string      `json:"stoppedReason"`
	StoppingAt         string      `json:"stoppingAt"`
	StoppedAt          string      `json:"stoppedAt"`
	Connectivity       string      `json:"connectivity"`
	ConnectivityAt     string      `json:"connectivityAt"`
	PullStartedAt      string      `json:"pullStartedAt"`
	PullStoppedAt      string      `json:"pullStoppedAt"`
	ExecutionStoppedAt string      `json:"executionStoppedAt"`
	CreatedAt          string      `json:"createdAt"`
	StartedAt          string      `json:"startedAt"`
	StartedBy          string      `json:"startedBy"`
	StopCode           string      `json:"stopCode"`
	Group              string      `json:"group"`
}

type Container struct {
	ContainerArn string `json:"containerArn"`
	Name         string `json:"name"`
	Image        string `json:"image"`
	LastStatus   string `json:"lastStatus"`
	ExitCode     *int   `json:"exitCode"`
	Reason       string `json:"reason"`
}

func handler(ctx context.Context, event events.CloudWatchEvent) error {
	log.Printf("Received ECS task state change event: %s", event.DetailType)

	// Parse the event detail
	var taskEvent ECSTaskStateChangeDetail
	err := json.Unmarshal(event.Detail, &taskEvent)
	if err != nil {
		log.Printf("Error unmarshaling event detail: %v", err)
		return err
	}

	// Only process STOPPED tasks
	if taskEvent.LastStatus != "STOPPED" {
		log.Printf("Task status is %s, not STOPPED. Ignoring.", taskEvent.LastStatus)
		return nil
	}

	log.Printf("Processing STOPPED task: %s", taskEvent.TaskArn)
	log.Printf("Stop reason: %s", taskEvent.StoppedReason)
	log.Printf("Stop code: %s", taskEvent.StopCode)

	// Extract task ID from ARN
	taskID := extractTaskID(taskEvent.TaskArn)
	if taskID == "" {
		log.Printf("Could not extract task ID from ARN: %s", taskEvent.TaskArn)
		return nil
	}

	// Find the execution associated with this task
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return err
	}

	ddbClient := dynamodb.NewFromConfig(cfg)
	tableName := models.GetTableName()

	// Query for execution with this task ARN
	execution, usecaseID, executionID, err := findExecutionByTaskArn(ctx, ddbClient, tableName, taskEvent.TaskArn)
	if err != nil {
		log.Printf("Error finding execution: %v", err)
		return err
	}

	if execution == nil {
		log.Printf("No execution found for task ARN: %s", taskEvent.TaskArn)
		return nil
	}

	log.Printf("Found execution: %s for usecase: %s", executionID, usecaseID)

	// Check if execution is already in a terminal state
	if execution.Status == "success" || execution.Status == "failed" || execution.Status == "stopped" || execution.Status == "error" {
		log.Printf("Execution already in terminal state: %s. Skipping update.", execution.Status)
		return nil
	}

	// Determine if this is a failure and get error message
	isFailure, errorMessage := analyzeTaskFailure(taskEvent)

	if isFailure {
		log.Printf("Task failed: %s", errorMessage)

		// Update execution status to failed
		completedAt := time.Now().UTC().Format(time.RFC3339)
		_, err = ddbClient.UpdateItem(ctx, &dynamodb.UpdateItemInput{
			TableName: aws.String(tableName),
			Key: map[string]types.AttributeValue{
				"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE_EXECUTION#%s", usecaseID)},
				"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("EXECUTION#%s", executionID)},
			},
			UpdateExpression: aws.String("SET #status = :status, completed_at = :completed_at, error_message = :error_msg"),
			ExpressionAttributeNames: map[string]string{
				"#status": "status",
			},
			ExpressionAttributeValues: map[string]types.AttributeValue{
				":status":       &types.AttributeValueMemberS{Value: "failed"},
				":completed_at": &types.AttributeValueMemberS{Value: completedAt},
				":error_msg":    &types.AttributeValueMemberS{Value: errorMessage},
			},
		})

		if err != nil {
			log.Printf("Error updating execution status: %v", err)
			return err
		}

		log.Printf("Updated execution %s to failed status", executionID)
	} else {
		log.Printf("Task stopped normally (user requested or successful completion)")
	}

	return nil
}

// extractTaskID extracts the task ID from the task ARN
func extractTaskID(taskArn string) string {
	// Task ARN format: arn:aws:ecs:region:account:task/cluster-name/task-id
	parts := strings.Split(taskArn, "/")
	if len(parts) > 0 {
		return parts[len(parts)-1]
	}
	return ""
}

// findExecutionByTaskArn finds an execution by its task ARN
func findExecutionByTaskArn(ctx context.Context, client *dynamodb.Client, tableName, taskArn string) (*models.Execution, string, string, error) {
	// We need to scan the table to find the execution with this task ARN
	// This is not ideal but task_arn is not a key field
	// In production, consider using a GSI on task_arn for better performance

	log.Printf("Scanning for execution with task ARN: %s", taskArn)

	// Use a filter expression to find the execution
	scanInput := &dynamodb.ScanInput{
		TableName:        aws.String(tableName),
		FilterExpression: aws.String("task_arn = :task_arn AND begins_with(pk, :pk_prefix)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":task_arn":  &types.AttributeValueMemberS{Value: taskArn},
			":pk_prefix": &types.AttributeValueMemberS{Value: "USECASE_EXECUTION#"},
		},
	}

	result, err := client.Scan(ctx, scanInput)
	if err != nil {
		return nil, "", "", err
	}

	if len(result.Items) == 0 {
		return nil, "", "", nil
	}

	// Parse the first matching execution
	var execution models.Execution
	err = attributevalue.UnmarshalMap(result.Items[0], &execution)
	if err != nil {
		return nil, "", "", err
	}

	// Extract usecase ID and execution ID from the keys
	usecaseID := strings.TrimPrefix(execution.PK, "USECASE_EXECUTION#")
	executionID := strings.TrimPrefix(execution.SK, "EXECUTION#")

	return &execution, usecaseID, executionID, nil
}

// analyzeTaskFailure determines if the task stopped due to a failure and returns an error message
func analyzeTaskFailure(detail ECSTaskStateChangeDetail) (bool, string) {
	// Check stop code - TaskFailedToStart indicates infrastructure issues
	if detail.StopCode == "TaskFailedToStart" {
		return true, fmt.Sprintf("Task failed to start: %s", detail.StoppedReason)
	}

	// Check if stopped reason indicates a failure
	stoppedReason := strings.ToLower(detail.StoppedReason)

	// Common failure patterns
	failurePatterns := []string{
		"cannotpullcontainererror",
		"resourceinitializationerror",
		"outofmemoryerror",
		"essential container",
		"failed",
		"error",
	}

	for _, pattern := range failurePatterns {
		if strings.Contains(stoppedReason, pattern) {
			return true, fmt.Sprintf("Task stopped due to error: %s", detail.StoppedReason)
		}
	}

	// Check container exit codes
	for _, container := range detail.Containers {
		if container.ExitCode != nil && *container.ExitCode != 0 {
			reason := container.Reason
			if reason == "" {
				reason = fmt.Sprintf("Container exited with code %d", *container.ExitCode)
			}
			return true, fmt.Sprintf("Container '%s' failed: %s", container.Name, reason)
		}

		// Check for container-level failures
		if container.Reason != "" {
			containerReason := strings.ToLower(container.Reason)
			for _, pattern := range failurePatterns {
				if strings.Contains(containerReason, pattern) {
					return true, fmt.Sprintf("Container '%s' failed: %s", container.Name, container.Reason)
				}
			}
		}
	}

	// If stopped reason is "User requested stop" or similar, it's not a failure
	if strings.Contains(stoppedReason, "user") || strings.Contains(stoppedReason, "scaling") {
		return false, ""
	}

	// If we can't determine, assume it's not a failure (worker might have updated status already)
	return false, ""
}

func main() {
	lambda.Start(handler)
}
