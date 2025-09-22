package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"sort"
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
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/google/uuid"
)

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

		_, err = ecsClient.RunTask(ctx, taskInput)
		if err != nil {
			log.Printf("Error starting ECS task: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}

		response, err = json.Marshal(map[string]string{
			"status":    "task started",
			"usecaseId": usecaseId,
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
