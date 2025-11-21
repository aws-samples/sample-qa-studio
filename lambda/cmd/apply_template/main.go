package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"sort"
	"time"

	"lambda/models"
	"lambda/utils"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/google/uuid"
)

type ApplyTemplateRequest struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	StartingURL string `json:"starting_url"`
}

type ApplyTemplateResponse struct {
	Success   bool   `json:"success"`
	UsecaseId string `json:"usecaseId"`
	Message   string `json:"message"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	templateId := request.PathParameters["id"]
	if templateId == "" {
		return events.APIGatewayProxyResponse{
			StatusCode: 400,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"success": false, "message": "Template ID is required"}`,
		}, nil
	}

	var applyReq ApplyTemplateRequest
	err := json.Unmarshal([]byte(request.Body), &applyReq)
	if err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 400}, err
	}

	if applyReq.Name == "" {
		return events.APIGatewayProxyResponse{
			StatusCode: 400,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"success": false, "message": "Name is required"}`,
		}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)

	// Get user claims for created_by tracking
	claims, err := utils.DecodeClaims(request)
	if err != nil {
		log.Printf("Error getting claims: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 401}, err
	}

	// Get template metadata
	templateResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("TEMPLATE#%s", templateId)},
			"sk": &types.AttributeValueMemberS{Value: "METADATA"},
		},
	})
	if err != nil {
		log.Printf("Error getting template: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	if templateResult.Item == nil {
		return events.APIGatewayProxyResponse{
			StatusCode: 404,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"success": false, "message": "Template not found"}`,
		}, nil
	}

	var template models.StepTemplate
	err = attributevalue.UnmarshalMap(templateResult.Item, &template)
	if err != nil {
		log.Printf("Error unmarshaling template: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Generate new usecase ID
	newUsecaseId := uuid.New().String()
	now := time.Now().UTC().Format(time.RFC3339)

	// Create new usecase with user-provided settings
	newUsecase := models.UseCase{
		PK:          "USECASES",
		SK:          fmt.Sprintf("USECASE#%s", newUsecaseId),
		ID:          newUsecaseId,
		Name:        applyReq.Name,
		Description: applyReq.Description,
		StartingURL: applyReq.StartingURL,
		Active:      true,
		Headless:    false,
		Region:      "eu-central-1",
		Tags:        []string{},
		CreatedAt:   now,
	}

	// Save new usecase
	usecaseItem, err := attributevalue.MarshalMap(newUsecase)
	if err != nil {
		log.Printf("Error marshaling new usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	_, err = client.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(models.GetTableName()),
		Item:      usecaseItem,
	})
	if err != nil {
		log.Printf("Error saving new usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Save created_by record
	createdByRecord := models.CreatedByRecord{
		PK:        fmt.Sprintf("USECASE#%s", newUsecaseId),
		SK:        "CREATED_BY",
		Email:     claims.Email,
		Sub:       claims.Sub,
		CreatedAt: now,
	}

	createdByItem, err := attributevalue.MarshalMap(createdByRecord)
	if err == nil {
		client.PutItem(ctx, &dynamodb.PutItemInput{
			TableName: aws.String(models.GetTableName()),
			Item:      createdByItem,
		})
	}

	// Copy steps from template
	stepsResult, err := client.Query(ctx, &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :sk)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("TEMPLATE#%s", templateId)},
			":sk": &types.AttributeValueMemberS{Value: "STEP#"},
		},
	})
	if err != nil {
		log.Printf("Error getting template steps: %v", err)
	} else {
		steps := make([]models.TemplateStep, 0)
		for _, item := range stepsResult.Items {
			var step models.TemplateStep
			err = attributevalue.UnmarshalMap(item, &step)
			if err != nil {
				log.Printf("Error unmarshaling step: %v", err)
				continue
			}
			steps = append(steps, step)
		}

		// Sort steps by Sort property
		sort.Slice(steps, func(i, j int) bool {
			return steps[i].Sort < steps[j].Sort
		})

		// Create new steps (they will be at the beginning since we start from sort 1)
		for _, step := range steps {
			newStepId := uuid.New().String()
			newStep := models.Step{
				PK:                 fmt.Sprintf("USECASE#%s", newUsecaseId),
				SK:                 fmt.Sprintf("STEP#%s", newStepId),
				Sort:               step.Sort,
				ID:                 newStepId,
				Instruction:        step.Instruction,
				StepType:           step.StepType,
				SecretKey:          step.SecretKey,
				CaptureVariable:    step.CaptureVariable,
				ValidationType:     step.ValidationType,
				ValidationOperator: step.ValidationOperator,
				ValidationValue:    step.ValidationValue,
				AssertionVariable:  step.AssertionVariable,
				CreatedAt:          now,
				ValueType:          step.ValueType,
			}

			stepItem, err := attributevalue.MarshalMap(newStep)
			if err != nil {
				log.Printf("Error marshaling new step: %v", err)
				continue
			}

			_, err = client.PutItem(ctx, &dynamodb.PutItemInput{
				TableName: aws.String(models.GetTableName()),
				Item:      stepItem,
			})
			if err != nil {
				log.Printf("Error saving new step: %v", err)
			}
		}
	}

	// Copy variables from template
	variablesResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("TEMPLATE#%s", templateId)},
			"sk": &types.AttributeValueMemberS{Value: "VARIABLES"},
		},
	})
	if err == nil && variablesResult.Item != nil {
		var templateVariables models.TemplateVariables
		err = attributevalue.UnmarshalMap(variablesResult.Item, &templateVariables)
		if err == nil && len(templateVariables.Variables) > 0 {
			newVariables := models.UsecaseVariables{
				PK:        fmt.Sprintf("USECASE#%s", newUsecaseId),
				SK:        "USECASE_VARIABLES",
				Variables: templateVariables.Variables,
				CreatedAt: now,
			}

			variablesItem, err := attributevalue.MarshalMap(newVariables)
			if err == nil {
				client.PutItem(ctx, &dynamodb.PutItemInput{
					TableName: aws.String(models.GetTableName()),
					Item:      variablesItem,
				})
			}
		}
	}

	// Create response
	response := ApplyTemplateResponse{
		Success:   true,
		UsecaseId: newUsecaseId,
		Message:   "Use case created from template successfully",
	}

	responseBody, err := json.Marshal(response)
	if err != nil {
		log.Printf("Error marshaling response: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	return events.APIGatewayProxyResponse{
		StatusCode: 200,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "POST, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(responseBody),
	}, nil
}

func main() {
	lambda.Start(handler)
}
