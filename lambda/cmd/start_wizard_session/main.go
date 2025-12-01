package main

import (
	"context"
	"encoding/json"
	"fmt"
	"lambda/models"
	"log"
	"os"
	"time"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/ecs"
	ecsTypes "github.com/aws/aws-sdk-go-v2/service/ecs/types"
	"github.com/google/uuid"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	var req models.StartWizardRequest
	if err := json.Unmarshal([]byte(request.Body), &req); err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 400}, err
	}

	// Validate required fields
	if req.Name == "" || req.StartingURL == "" {
		log.Printf("Missing required fields: name=%s, starting_url=%s", req.Name, req.StartingURL)
		return events.APIGatewayProxyResponse{
			StatusCode: 400,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"error": "name and starting_url are required"}`,
		}, nil
	}

	log.Printf("Starting wizard session: name=%s, starting_url=%s, region=%s", req.Name, req.StartingURL, req.Region)

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	ddbClient := dynamodb.NewFromConfig(cfg)
	ecsClient := ecs.NewFromConfig(cfg)

	// Generate IDs
	usecaseID, _ := uuid.NewV7()
	sessionID, _ := uuid.NewV7()
	createdAt := time.Now().UTC().Format(time.RFC3339)

	usecaseIDStr := usecaseID.String()
	sessionIDStr := sessionID.String()

	// Create use case record
	usecase := models.UseCase{
		PK:          "USECASES",
		SK:          fmt.Sprintf("USECASE#%s", usecaseIDStr),
		ID:          usecaseIDStr,
		Name:        req.Name,
		Description: req.Description,
		StartingURL: req.StartingURL,
		Active:      true,
		Headless:    false,
		Tags:        req.Tags,
		CreatedAt:   createdAt,
		Region:      req.Region,
	}

	usecaseItem, err := attributevalue.MarshalMap(usecase)
	if err != nil {
		log.Printf("Error marshaling usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	_, err = ddbClient.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(models.GetTableName()),
		Item:      usecaseItem,
	})
	if err != nil {
		log.Printf("Error creating usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Create wizard execution record
	execution := models.Execution{
		PK:           fmt.Sprintf("USECASE_EXECUTION#%s", usecaseIDStr),
		SK:           fmt.Sprintf("EXECUTION#%s", sessionIDStr),
		StartingURL:  req.StartingURL,
		Status:       "pending",
		Headless:     false,
		CreatedAt:    createdAt,
		TriggerType:  "Wizard",
		Region:       req.Region,
		Mode:         "wizard",
		WizardStatus: "active",
		LastActivity: createdAt,
	}

	log.Printf("Creating execution with starting_url: %s", execution.StartingURL)

	executionItem, err := attributevalue.MarshalMap(execution)
	if err != nil {
		log.Printf("Error marshaling execution: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	log.Printf("Execution item: %+v", executionItem)

	_, err = ddbClient.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(models.GetTableName()),
		Item:      executionItem,
	})
	if err != nil {
		log.Printf("Error creating execution: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	log.Printf("Successfully created execution %s for usecase %s", sessionIDStr, usecaseIDStr)

	// Start ECS task in wizard mode
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
					Environment: []ecsTypes.KeyValuePair{
						{Name: aws.String("WORKER_MODE"), Value: aws.String("wizard")},
						{Name: aws.String("SESSION_ID"), Value: aws.String(sessionIDStr)},
						{Name: aws.String("USECASE_ID"), Value: aws.String(usecaseIDStr)},
						{Name: aws.String("WIZARD_QUEUE_URL"), Value: aws.String(os.Getenv("WIZARD_QUEUE_URL"))},
						{Name: aws.String("DYNAMODB_TABLE_NAME"), Value: aws.String(models.GetTableName())},
						{Name: aws.String("S3_BUCKET"), Value: aws.String(os.Getenv("S3_BUCKET"))},
						{Name: aws.String("BEDROCK_EXECUTION_ROLE"), Value: aws.String(os.Getenv("BEDROCK_EXECUTION_ROLE"))},
						{Name: aws.String("NOVA_ACT_API_KEY_NAME"), Value: aws.String(os.Getenv("NOVA_ACT_API_KEY_NAME"))},
					},
				},
			},
		},
	}

	_, err = ecsClient.RunTask(ctx, taskInput)
	if err != nil {
		log.Printf("Error starting ECS task: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response, _ := json.Marshal(models.WizardSessionResponse{
		SessionID: sessionIDStr,
		UsecaseID: usecaseIDStr,
		Status:    "initializing",
	})

	return events.APIGatewayProxyResponse{
		StatusCode: 201,
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
