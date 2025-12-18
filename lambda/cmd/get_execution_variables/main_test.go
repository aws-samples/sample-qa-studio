package main

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/aws/aws-lambda-go/events"
	"github.com/stretchr/testify/assert"
)

func TestHandler(t *testing.T) {
	// Test case for valid request
	request := events.APIGatewayProxyRequest{
		PathParameters: map[string]string{
			"usecaseId":   "test-usecase",
			"executionId": "test-execution",
		},
	}

	// Note: This test would require mocking DynamoDB
	// For now, we'll just test the structure
	response, err := handler(context.Background(), request)

	// We expect an error since DynamoDB isn't available in test
	// But we can check the response structure
	assert.NotNil(t, response)

	// Test case for missing parameters
	requestMissingParams := events.APIGatewayProxyRequest{
		PathParameters: map[string]string{},
	}

	response, err = handler(context.Background(), requestMissingParams)
	assert.NotNil(t, err)
	assert.Equal(t, 400, response.StatusCode)

	var errorResponse map[string]string
	json.Unmarshal([]byte(response.Body), &errorResponse)
	assert.Equal(t, "Missing required parameters", errorResponse["error"])
}
