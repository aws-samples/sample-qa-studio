package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/url"
	"os"
	"sort"
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
	"github.com/aws/aws-sdk-go-v2/service/ecs"
	ecsTypes "github.com/aws/aws-sdk-go-v2/service/ecs/types"
	"github.com/aws/aws-sdk-go-v2/service/eventbridge"
	eventbridgeTypes "github.com/aws/aws-sdk-go-v2/service/eventbridge/types"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/google/uuid"
)

// generateCloudWatchLogsURL creates a deep link to CloudWatch Logs for a specific ECS task
func generateCloudWatchLogsURL(region, logGroup, streamPrefix, taskID string) string {
	// CloudWatch Logs URL format for ECS task logs
	// The log stream name for ECS tasks with awsLogs driver is: {streamPrefix}/{container-name}/{task-id}
	logStreamName := fmt.Sprintf("%s/container/%s", streamPrefix, taskID)

	return fmt.Sprintf(
		"https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#logsV2:log-groups/log-group/%s/log-events/%s",
		region,
		region,
		url.PathEscape(logGroup),
		url.PathEscape(logStreamName),
	)
}

// updateExecutionTaskInfo updates the execution record with ECS task metadata
func updateExecutionTaskInfo(ctx context.Context, ddbClient *dynamodb.Client, usecaseID, executionID, taskArn, taskID, cloudWatchURL string) error {
	_, err := ddbClient.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE_EXECUTION#%s", usecaseID)},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("EXECUTION#%s", executionID)},
		},
		UpdateExpression: aws.String("SET task_arn = :task_arn, task_id = :task_id, cloudwatch_logs_url = :cloudwatch_url"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":task_arn":       &types.AttributeValueMemberS{Value: taskArn},
			":task_id":        &types.AttributeValueMemberS{Value: taskID},
			":cloudwatch_url": &types.AttributeValueMemberS{Value: cloudWatchURL},
		},
	})

	if err != nil {
		log.Printf("Error updating execution task info: %v", err)
		return err
	}

	log.Printf("Updated execution %s with task ARN: %s, task ID: %s", executionID, taskArn, taskID)
	return nil
}

// publishExecutionStatusEvent publishes an execution status change event to EventBridge
func publishExecutionStatusEvent(ctx context.Context, usecaseID, executionID, status string) error {
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config for EventBridge: %v", err)
		return err
	}

	eventsClient := eventbridge.NewFromConfig(cfg)

	eventDetail := map[string]string{
		"usecase_id":   usecaseID,
		"execution_id": executionID,
		"status":       status,
		"timestamp":    time.Now().UTC().Format(time.RFC3339),
	}

	detailJSON, err := json.Marshal(eventDetail)
	if err != nil {
		log.Printf("Error marshaling event detail: %v", err)
		return err
	}

	_, err = eventsClient.PutEvents(ctx, &eventbridge.PutEventsInput{
		Entries: []eventbridgeTypes.PutEventsRequestEntry{
			{
				Source:       aws.String("nova-act-qa-studio.execution"),
				DetailType:   aws.String("nova-act-qa-studio.execution.status.changed"),
				Detail:       aws.String(string(detailJSON)),
				EventBusName: aws.String("default"),
			},
		},
	})

	if err != nil {
		log.Printf("Error publishing event to EventBridge: %v", err)
		// Don't fail the execution if event publishing fails
		return nil
	}

	log.Printf("Published execution status event: %s/%s -> %s", usecaseID, executionID, status)
	return nil
}

// updateExecutionStatusWithError updates execution status and logs error details
func updateExecutionStatusWithError(ctx context.Context, ddbClient *dynamodb.Client, usecaseID, executionID, status, errorMsg string) error {
	completedAt := time.Now().UTC().Format(time.RFC3339)

	_, err := ddbClient.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE_EXECUTION#%s", usecaseID)},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("EXECUTION#%s", executionID)},
		},
		UpdateExpression: aws.String("SET #status = :status, completed_at = :completed_at, error_message = :error_msg"),
		ExpressionAttributeNames: map[string]string{
			"#status": "status",
		},
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":status":       &types.AttributeValueMemberS{Value: status},
			":completed_at": &types.AttributeValueMemberS{Value: completedAt},
			":error_msg":    &types.AttributeValueMemberS{Value: errorMsg},
		},
	})

	if err != nil {
		log.Printf("Error updating execution status: %v", err)
		return err
	}

	log.Printf("Updated execution %s status to %s with error: %s", executionID, status, errorMsg)

	// Publish event to EventBridge
	publishExecutionStatusEvent(ctx, usecaseID, executionID, status)

	return nil
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseId := request.PathParameters["id"]
	if usecaseId == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	triggerType := request.QueryStringParameters["trigger-type"]
	if triggerType == "" {
		triggerType = "OnDemand"
	}

	log.Println("usecaseID", usecaseId, "triggertype", triggerType)

	createdAtTime := time.Now().UTC().Format(time.RFC3339)

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	ddbClient := dynamodb.NewFromConfig(cfg)
	sqsClient := sqs.NewFromConfig(cfg)

	// Load usecase first
	usecaseResult, err := ddbClient.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "USECASES"},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", usecaseId)},
		},
	})
	if err != nil {
		log.Printf("Error loading usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	var usecase models.UseCase
	err = attributevalue.UnmarshalMap(usecaseResult.Item, &usecase)
	if err != nil {
		log.Printf("Error unmarshaling usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	idObject, err := uuid.NewV7()
	if err != nil {
		log.Printf("Error generating UUID: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	executionId := idObject.String()

	headless := false
	if usecase.Headless {
		headless = true
	}

	// override in case of scheduled task or OnDemandHeadless
	if triggerType == "Scheduled" || triggerType == "OnDemandHeadless" {
		headless = true
	}

	// Create execution record
	execution := models.Execution{
		PK:          fmt.Sprintf("USECASE_EXECUTION#%s", usecaseId),
		SK:          "EXECUTION#" + executionId,
		StartingURL: usecase.StartingURL,
		Status:      "pending",
		Headless:    headless,
		CreatedAt:   createdAtTime,
		TriggerType: triggerType,
		Region:      usecase.Region,
	}

	item, err := attributevalue.MarshalMap(execution)
	if err != nil {
		log.Printf("Error marshaling execution: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	_, err = ddbClient.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(models.GetTableName()),
		Item:      item,
	})
	if err != nil {
		log.Printf("Error creating execution: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Publish event for pending status
	publishExecutionStatusEvent(ctx, usecaseId, executionId, "pending")

	// Load steps for this usecase
	input := &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :usecaseId AND begins_with(sk, :prefix)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":usecaseId": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", usecaseId)},
			":prefix":    &types.AttributeValueMemberS{Value: "STEP#"},
		},
	}

	result, err := ddbClient.Query(ctx, input)
	if err != nil {
		log.Printf("Error querying steps: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	var steps []models.Step
	err = attributevalue.UnmarshalListOfMaps(result.Items, &steps)
	if err != nil {
		log.Printf("Error unmarshaling steps: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Sort steps by sort field
	sort.Slice(steps, func(i, j int) bool {
		return steps[i].Sort < steps[j].Sort
	})

	// Create execution step records
	for _, step := range steps {
		idObject, err := uuid.NewV7()
		if err != nil {
			log.Printf("Error creating execution step id: %v", err)
		}

		id := idObject.String()

		executionStep := models.ExecutionStep{
			PK:                 "EXECUTION#" + executionId,
			SK:                 "EXECUTION_STEP#" + id,
			Instruction:        step.Instruction,
			StepID:             step.ID,
			Sort:               step.Sort,
			StepType:           step.StepType,
			SecretKey:          step.SecretKey,
			ValidationType:     step.ValidationType,
			ValidationOperator: step.ValidationOperator,
			ValidationValue:    step.ValidationValue,
			CaptureVariable:    step.CaptureVariable,
			CreatedAt:          createdAtTime,
			AssertionVariable:  step.AssertionVariable,
			ValueType:          step.ValueType,
		}

		stepItem, err := attributevalue.MarshalMap(executionStep)
		if err != nil {
			log.Printf("Error marshaling execution step: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}

		_, err = ddbClient.PutItem(ctx, &dynamodb.PutItemInput{
			TableName: aws.String(models.GetTableName()),
			Item:      stepItem,
		})
		if err != nil {
			log.Printf("Error creating execution step: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}
	}

	// Load hooks and store them with execution
	hooksResult, err := ddbClient.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", usecaseId)},
			"sk": &types.AttributeValueMemberS{Value: "HOOKS"},
		},
	})
	if err != nil {
		log.Printf("Error loading hooks: %v", err)
	} else if hooksResult.Item != nil {
		type Hooks struct {
			BeforeScript string `dynamodbav:"before_script"`
			AfterScript  string `dynamodbav:"after_script"`
		}
		var hooks Hooks
		err = attributevalue.UnmarshalMap(hooksResult.Item, &hooks)
		if err != nil {
			log.Printf("Error unmarshaling hooks: %v", err)
		} else {
			executionHooks := map[string]interface{}{
				"pk":            "EXECUTION#" + executionId,
				"sk":            "HOOKS",
				"before_script": hooks.BeforeScript,
				"after_script":  hooks.AfterScript,
				"created_at":    createdAtTime,
			}

			hooksItem, err := attributevalue.MarshalMap(executionHooks)
			if err != nil {
				log.Printf("Error marshaling execution hooks: %v", err)
			} else {
				_, err = ddbClient.PutItem(ctx, &dynamodb.PutItemInput{
					TableName: aws.String(models.GetTableName()),
					Item:      hooksItem,
				})
				if err != nil {
					log.Printf("Error creating execution hooks: %v", err)
				}
			}
		}
	}

	// Load usecase variables and create execution variables
	variablesResult, err := ddbClient.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", usecaseId)},
			"sk": &types.AttributeValueMemberS{Value: "USECASE_VARIABLES"},
		},
	})
	if err != nil {
		log.Printf("Error loading variables: %v", err)
	} else if variablesResult.Item != nil {
		var usecaseVariables models.UsecaseVariables
		err = attributevalue.UnmarshalMap(variablesResult.Item, &usecaseVariables)
		if err != nil {
			log.Printf("Error unmarshaling variables: %v", err)
		} else {
			executionVariables := models.ExecutionVariables{
				PK:        "EXECUTION#" + executionId,
				SK:        "EXECUTION_VARIABLES",
				Variables: usecaseVariables.Variables,
				CreatedAt: createdAtTime,
			}

			variablesItem, err := attributevalue.MarshalMap(executionVariables)
			if err != nil {
				log.Printf("Error marshaling execution variables: %v", err)
			} else {
				_, err = ddbClient.PutItem(ctx, &dynamodb.PutItemInput{
					TableName: aws.String(models.GetTableName()),
					Item:      variablesItem,
				})
				if err != nil {
					log.Printf("Error creating execution variables: %v", err)
				}
			}
		}
	}

	// Load usecase headers and create execution headers
	headersResult, err := ddbClient.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", usecaseId)},
			"sk": &types.AttributeValueMemberS{Value: "HEADERS"},
		},
	})
	if err != nil {
		log.Printf("Error loading headers: %v", err)
	} else if headersResult.Item != nil {
		var usecaseHeaders models.UsecaseHeaders
		err = attributevalue.UnmarshalMap(headersResult.Item, &usecaseHeaders)
		if err != nil {
			log.Printf("Error unmarshaling headers: %v", err)
		} else {
			executionHeaders := models.ExecutionHeaders{
				PK:        "EXECUTION#" + executionId,
				SK:        "HEADERS",
				Headers:   usecaseHeaders.Headers,
				CreatedAt: createdAtTime,
			}

			headersItem, err := attributevalue.MarshalMap(executionHeaders)
			if err != nil {
				log.Printf("Error marshaling execution headers: %v", err)
			} else {
				_, err = ddbClient.PutItem(ctx, &dynamodb.PutItemInput{
					TableName: aws.String(models.GetTableName()),
					Item:      headersItem,
				})
				if err != nil {
					log.Printf("Error creating execution headers: %v", err)
				}
			}
		}
	}

	var response []byte

	if triggerType == "OnDemand" {
		queueMessage := models.QueueMessage{
			ExecutionID: executionId,
			UsecaseID:   usecaseId,
		}

		jsonData, err := json.Marshal(queueMessage)
		if err != nil {
			log.Printf("Error creating execution step: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}

		// Send message to queue
		_, err = sqsClient.SendMessage(ctx, &sqs.SendMessageInput{
			QueueUrl:    aws.String(os.Getenv("QUEUE_URL")),
			MessageBody: aws.String(string(jsonData)),
		})
		if err != nil {
			log.Printf("Error sending message: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}
		response, err = json.Marshal(map[string]string{
			"status":    "usecase queued",
			"usecaseId": usecaseId,
		})
		if err != nil {
			log.Printf("Error marshaling response: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}
	}

	if triggerType == "Scheduled" || triggerType == "OnDemandHeadless" {
		ecsClient := ecs.NewFromConfig(cfg)

		log.Println("Trigger ECS", usecaseId, executionId)

		// Create ECS task
		taskInput := &ecs.RunTaskInput{
			Cluster:        aws.String(os.Getenv("ECS_CLUSTER")),
			TaskDefinition: aws.String(os.Getenv("ECS_TASK_DEFINITION")),
			LaunchType:     ecsTypes.LaunchTypeFargate,
			NetworkConfiguration: &ecsTypes.NetworkConfiguration{
				AwsvpcConfiguration: &ecsTypes.AwsVpcConfiguration{
					Subnets:        []string{os.Getenv("SUBNET_ID")},
					SecurityGroups: []string{os.Getenv("SECURITY_GROUP_ID")},
					AssignPublicIp: ecsTypes.AssignPublicIpEnabled,
				},
			},
			Overrides: &ecsTypes.TaskOverride{
				ContainerOverrides: []ecsTypes.ContainerOverride{
					{
						Name: aws.String("container"),
						// Command: []string{"bash", "-c", fmt.Sprintf("source .venv/bin/activate && ./worker -mode ecs -executionId %s -usecaseId %s", executionId, usecaseId)},
						Environment: []ecsTypes.KeyValuePair{
							{
								Name:  aws.String("AWS_REGION"),
								Value: aws.String(os.Getenv("AWS_REGION")),
							},
							{
								Name:  aws.String("EXECUTION_ID"),
								Value: aws.String(executionId),
							},
							{
								Name:  aws.String("USECASE_ID"),
								Value: aws.String(usecaseId),
							},
							{
								Name:  aws.String("DYNAMODB_TABLE_NAME"),
								Value: aws.String(os.Getenv("TABLE_NAME")),
							},
							{
								Name:  aws.String("S3_BUCKET"),
								Value: aws.String(os.Getenv("S3_BUCKET")),
							},
							{
								Name:  aws.String("USER_AGENT"),
								Value: aws.String(os.Getenv("USER_AGENT")),
							},
							{
								Name:  aws.String("BEDROCK_EXECUTION_ROLE"),
								Value: aws.String(os.Getenv("BEDROCK_EXECUTION_ROLE")),
							},
							{
								Name:  aws.String("NOVA_ACT_API_KEY_NAME"),
								Value: aws.String(os.Getenv("NOVA_ACT_API_KEY_NAME")),
							},
							{
								Name:  aws.String("SECRETS_PREFIX"),
								Value: aws.String(os.Getenv("SECRETS_PREFIX")),
							},
						},
					},
				},
			},
		}

		taskResult, err := ecsClient.RunTask(ctx, taskInput)
		if err != nil {
			log.Printf("Error starting ECS task: %v", err)
			updateExecutionStatusWithError(ctx, ddbClient, usecaseId, executionId, "failed", fmt.Sprintf("Failed to start ECS task: %v", err))
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}

		// Check for task failures
		if len(taskResult.Failures) > 0 {
			failure := taskResult.Failures[0]
			errorMsg := fmt.Sprintf("Task failed to start - Reason: %s, Detail: %s",
				aws.ToString(failure.Reason),
				aws.ToString(failure.Detail))
			log.Printf("ECS task failure: %s", errorMsg)

			updateExecutionStatusWithError(ctx, ddbClient, usecaseId, executionId, "failed", errorMsg)

			return events.APIGatewayProxyResponse{
				StatusCode: 500,
				Headers: map[string]string{
					"Content-Type":                 "application/json",
					"Access-Control-Allow-Origin":  "*",
					"Access-Control-Allow-Methods": "POST, OPTIONS",
					"Access-Control-Allow-Headers": "Content-Type, Authorization",
				},
				Body: fmt.Sprintf(`{"error": "%s"}`, errorMsg),
			}, fmt.Errorf("task failed to start")
		}

		// Verify at least one task was created
		if len(taskResult.Tasks) == 0 {
			errorMsg := "No tasks were created by ECS RunTask"
			log.Printf("ECS error: %s", errorMsg)
			updateExecutionStatusWithError(ctx, ddbClient, usecaseId, executionId, "failed", errorMsg)

			return events.APIGatewayProxyResponse{
				StatusCode: 500,
				Headers: map[string]string{
					"Content-Type":                 "application/json",
					"Access-Control-Allow-Origin":  "*",
					"Access-Control-Allow-Methods": "POST, OPTIONS",
					"Access-Control-Allow-Headers": "Content-Type, Authorization",
				},
				Body: fmt.Sprintf(`{"error": "%s"}`, errorMsg),
			}, fmt.Errorf("%s", errorMsg)
		}

		// Extract task ARN and ID
		task := taskResult.Tasks[0]
		taskArn := aws.ToString(task.TaskArn)

		// Extract task ID from ARN (format: arn:aws:ecs:region:account:task/cluster-name/task-id)
		taskID := taskArn
		if lastSlash := strings.LastIndex(taskArn, "/"); lastSlash != -1 {
			taskID = taskArn[lastSlash+1:]
		}

		log.Printf("ECS task started - ARN: %s, ID: %s", taskArn, taskID)

		// Generate CloudWatch Logs URL
		region := os.Getenv("AWS_REGION")
		logGroup := os.Getenv("LOG_GROUP_NAME")
		if logGroup == "" {
			logGroup = "/ecs/nova-act-worker" // Default log group name
		}

		streamPrefix := os.Getenv("LOG_STREAM_PREFIX")
		if streamPrefix == "" {
			streamPrefix = "ecs" // Default stream prefix
		}

		cloudWatchURL := generateCloudWatchLogsURL(region, logGroup, streamPrefix, taskID)
		log.Printf("CloudWatch Logs URL: %s", cloudWatchURL)

		// Update execution with task metadata
		err = updateExecutionTaskInfo(ctx, ddbClient, usecaseId, executionId, taskArn, taskID, cloudWatchURL)
		if err != nil {
			log.Printf("Warning: Failed to update task info in DynamoDB: %v", err)
			// Don't fail the request, task is already running
		}

		response, err = json.Marshal(map[string]interface{}{
			"status":            "task started",
			"usecaseId":         usecaseId,
			"executionId":       executionId,
			"taskArn":           taskArn,
			"taskId":            taskID,
			"cloudWatchLogsUrl": cloudWatchURL,
		})
		if err != nil {
			log.Printf("Error marshaling response: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}
	}

	return events.APIGatewayProxyResponse{
		StatusCode: 200,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "POST, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(response),
	}, nil
}

func main() {
	lambda.Start(handler)
}
