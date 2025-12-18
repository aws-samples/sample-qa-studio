package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
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
	"github.com/google/uuid"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseID := request.PathParameters["id"]
	if usecaseID == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400, Body: "Missing usecase ID"}, nil
	}

	var req models.ImportTemplateRequest
	if err := json.Unmarshal([]byte(request.Body), &req); err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 400}, err
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)

	// 1. Get template metadata to get current version
	templateResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "TEMPLATE#" + req.TemplateID},
			"sk": &types.AttributeValueMemberS{Value: "METADATA"},
		},
	})
	if err != nil {
		log.Printf("Error getting template: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	if templateResult.Item == nil {
		return events.APIGatewayProxyResponse{StatusCode: 404, Body: "Template not found"}, nil
	}

	var template models.StepTemplate
	err = attributevalue.UnmarshalMap(templateResult.Item, &template)
	if err != nil {
		log.Printf("Error unmarshaling template: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// 2. Get template steps
	stepsResult, err := client.Query(ctx, &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :sk)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk": &types.AttributeValueMemberS{Value: "TEMPLATE#" + req.TemplateID},
			":sk": &types.AttributeValueMemberS{Value: "STEP#"},
		},
	})
	if err != nil {
		log.Printf("Error querying template steps: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	var templateSteps []models.TemplateStep
	err = attributevalue.UnmarshalListOfMaps(stepsResult.Items, &templateSteps)
	if err != nil {
		log.Printf("Error unmarshaling template steps: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	log.Printf("Template has %d steps (before sorting)", len(templateSteps))
	for i, step := range templateSteps {
		log.Printf("BEFORE SORT - Template step %d: sort=%d, instruction=%s", i, step.Sort, step.Instruction)
	}

	// Sort template steps by sort order
	sort.Slice(templateSteps, func(i, j int) bool {
		return templateSteps[i].Sort < templateSteps[j].Sort
	})

	log.Printf("Template has %d steps (after sorting)", len(templateSteps))
	for i, step := range templateSteps {
		log.Printf("AFTER SORT - Template step %d: sort=%d, instruction=%s", i, step.Sort, step.Instruction)
	}

	// 3. Get existing use case steps to determine insertion point
	existingStepsResult, err := client.Query(ctx, &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :sk)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk": &types.AttributeValueMemberS{Value: "USECASE#" + usecaseID},
			":sk": &types.AttributeValueMemberS{Value: "STEP#"},
		},
	})
	if err != nil {
		log.Printf("Error querying existing steps: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	var existingSteps []models.Step
	err = attributevalue.UnmarshalListOfMaps(existingStepsResult.Items, &existingSteps)
	if err != nil {
		log.Printf("Error unmarshaling existing steps: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Sort existing steps
	sort.Slice(existingSteps, func(i, j int) bool {
		return existingSteps[i].Sort < existingSteps[j].Sort
	})

	// 4. Calculate new sort orders
	insertPosition := req.InsertPosition
	if insertPosition == -1 {
		// Insert at end
		if len(existingSteps) > 0 {
			insertPosition = existingSteps[len(existingSteps)-1].Sort + 1
		} else {
			insertPosition = 1 // Use 1-based indexing to match use case convention
		}
	} else if insertPosition == 0 {
		// Insert at beginning - use 1-based indexing
		insertPosition = 1
	}

	// 5. Create new steps from template
	var newSteps []models.Step
	now := time.Now().UTC().Format(time.RFC3339)

	log.Printf("Insert position: %d", insertPosition)

	for i, templateStep := range templateSteps {
		idObject, err := uuid.NewV7()
		if err != nil {
			log.Printf("Error generating UUID: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}

		newSortOrder := insertPosition + i
		log.Printf("Creating step %d with sort order %d from template step with sort %d", i, newSortOrder, templateStep.Sort)

		newStep := models.Step{
			PK:                 fmt.Sprintf("USECASE#%s", usecaseID),
			SK:                 "STEP#" + idObject.String(),
			ID:                 idObject.String(),
			Sort:               newSortOrder,
			Instruction:        templateStep.Instruction,
			StepType:           templateStep.StepType,
			SecretKey:          templateStep.SecretKey,
			CaptureVariable:    templateStep.CaptureVariable,
			ValidationType:     templateStep.ValidationType,
			ValidationOperator: templateStep.ValidationOperator,
			ValidationValue:    templateStep.ValidationValue,
			AssertionVariable:  templateStep.AssertionVariable,
			ValueType:          templateStep.ValueType,
			CreatedAt:          now,
			// Template reference fields
			TemplateID:      req.TemplateID,
			TemplateStepID:  templateStep.ID,
			TemplateVersion: template.Version,
		}
		newSteps = append(newSteps, newStep)
	}

	// 6. Update sort orders for steps after insertion point
	var updatedSteps []models.Step
	for _, step := range existingSteps {
		if step.Sort >= insertPosition {
			step.Sort += len(templateSteps)
			updatedSteps = append(updatedSteps, step)
		}
	}

	// 7. Write all changes to DynamoDB SEQUENTIALLY to avoid race conditions
	log.Printf("Writing %d new steps to DynamoDB SEQUENTIALLY", len(newSteps))

	// Write new steps ONE AT A TIME in order
	for i, step := range newSteps {
		log.Printf("Writing new step %d: sort=%d, instruction=%s", i, step.Sort, step.Instruction)
		item, err := attributevalue.MarshalMap(step)
		if err != nil {
			log.Printf("Error marshaling step: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}

		_, err = client.PutItem(ctx, &dynamodb.PutItemInput{
			TableName: aws.String(models.GetTableName()),
			Item:      item,
		})
		if err != nil {
			log.Printf("Error writing step %d: %v", i, err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}
		log.Printf("Successfully wrote step %d with sort=%d", i, step.Sort)
	}

	// Update existing steps ONE AT A TIME
	log.Printf("Updating %d existing steps", len(updatedSteps))
	for i, step := range updatedSteps {
		log.Printf("Updating existing step %d: sort=%d", i, step.Sort)
		item, err := attributevalue.MarshalMap(step)
		if err != nil {
			log.Printf("Error marshaling step: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}

		_, err = client.PutItem(ctx, &dynamodb.PutItemInput{
			TableName: aws.String(models.GetTableName()),
			Item:      item,
		})
		if err != nil {
			log.Printf("Error updating step %d: %v", i, err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}
	}

	log.Printf("Successfully wrote all %d steps sequentially", len(newSteps))

	// 8. Get template variables and merge with use case variables
	templateVarsResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			":pk": &types.AttributeValueMemberS{Value: "TEMPLATE#" + req.TemplateID},
			":sk": &types.AttributeValueMemberS{Value: "VARIABLES"},
		},
	})
	if err == nil && templateVarsResult.Item != nil {
		var templateVars models.TemplateVariables
		err = attributevalue.UnmarshalMap(templateVarsResult.Item, &templateVars)
		if err == nil && len(templateVars.Variables) > 0 {
			// Get existing use case variables
			usecaseVarsResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
				TableName: aws.String(models.GetTableName()),
				Key: map[string]types.AttributeValue{
					"pk": &types.AttributeValueMemberS{Value: "USECASE#" + usecaseID},
					"sk": &types.AttributeValueMemberS{Value: "VARIABLES"},
				},
			})

			var usecaseVars models.UsecaseVariables
			if err == nil && usecaseVarsResult.Item != nil {
				attributevalue.UnmarshalMap(usecaseVarsResult.Item, &usecaseVars)
			} else {
				usecaseVars = models.UsecaseVariables{
					PK:        "USECASE#" + usecaseID,
					SK:        "VARIABLES",
					Variables: []models.KeyValuePair{},
					CreatedAt: now,
				}
			}

			// Merge variables (don't overwrite existing ones)
			existingKeys := make(map[string]bool)
			for _, v := range usecaseVars.Variables {
				existingKeys[v.Key] = true
			}

			for _, templateVar := range templateVars.Variables {
				if !existingKeys[templateVar.Key] {
					usecaseVars.Variables = append(usecaseVars.Variables, templateVar)
				}
			}

			// Save merged variables
			varsItem, err := attributevalue.MarshalMap(usecaseVars)
			if err == nil {
				client.PutItem(ctx, &dynamodb.PutItemInput{
					TableName: aws.String(models.GetTableName()),
					Item:      varsItem,
				})
			}
		}
	}

	response := map[string]interface{}{
		"message":       "Template imported successfully",
		"steps_created": len(newSteps),
	}
	body, err := json.Marshal(response)
	if err != nil {
		log.Printf("Error marshaling response: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	return events.APIGatewayProxyResponse{
		StatusCode: 201,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "POST, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(body),
	}, nil
}

func main() {
	lambda.Start(handler)
}
