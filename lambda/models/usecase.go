package models

import (
	"log"
	"os"
)

// GetTableName returns the DynamoDB table name from environment variable
func GetTableName() string {
	tableName := os.Getenv("TABLE_NAME")
	if tableName == "" {
		// Fallback to default for backward compatibility
		log.Println("environment variable 'TABLE_NAME' missing")
		return "accept-ai"
	}
	return tableName
}

// GetSecretPrefix returns the secret prefix for usecase secrets
func GetSecretPrefix() string {
	tableName := GetTableName()
	return tableName
}

// GetBucketName returns the S3 bucket name from environment variable
func GetBucketName() string {
	bucketName := os.Getenv("BUCKET_NAME")
	if bucketName == "" {
		// Fallback to default for backward compatibility
		return "accept-ai-artefacts"
	}
	return bucketName
}

type UseCase struct {
	PK                  string   `json:"pk" dynamodbav:"pk"`
	SK                  string   `json:"sk" dynamodbav:"sk"`
	ID                  string   `json:"id" dynamodbav:"id"`
	Name                string   `json:"name" dynamodbav:"name"`
	Description         string   `json:"description" dynamodbav:"description"`
	StartingURL         string   `json:"starting_url" dynamodbav:"starting_url"`
	Active              bool     `json:"active" dynamodbav:"active"`
	Headless            bool     `json:"headless" dynamodbav:"headless"`
	Tags                []string `json:"tags" dynamodbav:"tags"`
	CreatedAt           string   `json:"createdAt" dynamodbav:"createdAt"`
	Region              string   `json:"region" dynamodbav:"execution_region"`
	LastExecutionID     string   `json:"last_execution_id,omitempty" dynamodbav:"last_execution_id,omitempty"`
	LastExecutionStatus string   `json:"last_execution_status,omitempty" dynamodbav:"last_execution_status,omitempty"`
	LastExecutionTime   string   `json:"last_execution_time,omitempty" dynamodbav:"last_execution_time,omitempty"`
}

type CreateUsecaseRequest struct {
	Name        string   `json:"name"`
	Description string   `json:"description"`
	StartingURL string   `json:"starting_url"`
	Active      bool     `json:"active"`
	Headless    bool     `json:"headless"`
	Tags        []string `json:"tags"`
	Region      string   `json:"region"`
}

type UpdateUsecaseRequest struct {
	Name        string   `json:"name"`
	Description string   `json:"description"`
	StartingURL string   `json:"starting_url"`
	Active      bool     `json:"active"`
	Headless    bool     `json:"headless"`
	Tags        []string `json:"tags"`
	Region      string   `json:"region"`
}

type Step struct {
	PK                 string `json:"pk" dynamodbav:"pk"`
	SK                 string `json:"sk" dynamodbav:"sk"`
	Sort               int    `json:"sort" dynamodbav:"sort"`
	ID                 string `json:"id" dynamodbav:"id"`
	Instruction        string `json:"instruction" dynamodbav:"instruction"`
	StepType           string `json:"step_type" dynamodbav:"step_type"`                       // "navigation", "secret", "validation", "retrieve_value", or "assertion"
	SecretKey          string `json:"secret_key,omitempty" dynamodbav:"secret_key,omitempty"` // Only for secret steps
	CaptureVariable    string `json:"capture_variable,omitempty" dynamodbav:"capture_variable,omitempty"`
	ValidationType     string `json:"validation_type,omitempty" dynamodbav:"validation_type,omitempty"`         // "bool" or "string"
	ValidationOperator string `json:"validation_operator,omitempty" dynamodbav:"validation_operator,omitempty"` // "exact" or "contains" (for string validation)
	ValidationValue    string `json:"validation_value,omitempty" dynamodbav:"validation_value,omitempty"`       // Expected value for validation
	AssertionVariable  string `json:"assertion_variable,omitempty" dynamodbav:"assertion_variable,omitempty"`   // Runtime variable name for assertion steps
	CreatedAt          string `json:"createdAt" dynamodbav:"createdAt"`
	ValueStep          string `json:"value_step,omitempty" dynamodbav:"value_step,omitempty"`
	ValueType          string `json:"value_type,omitempty" dynamodbav:"value_type,omitempty"`
	// Template reference fields
	TemplateID      string `json:"template_id,omitempty" dynamodbav:"template_id,omitempty"`
	TemplateStepID  string `json:"template_step_id,omitempty" dynamodbav:"template_step_id,omitempty"`
	TemplateVersion int    `json:"template_version,omitempty" dynamodbav:"template_version,omitempty"`
}

type Execution struct {
	PK                string `json:"pk" dynamodbav:"pk"`
	SK                string `json:"sk" dynamodbav:"sk"`
	Status            string `json:"status" dynamodbav:"status"`
	StartingURL       string `json:"starting_url" dynamodbav:"starting_url"`
	Headless          bool   `json:"headless" dynamodbav:"headless"`
	CreatedAt         string `json:"createdAt" dynamodbav:"created_at"`
	CompletedAt       string `json:"completedAt" dynamodbav:"completed_at"`
	ExecutingAt       string `json:"executingAt" dynamodbav:"executing_at"`
	TriggerType       string `json:"triggerType" dynamodbav:"trigger_type"`
	NovaActSessionID  string `json:"novaActSessionId" dynamodbav:"nova_session_id"`
	Region            string `json:"region" dynamodbav:"execution_region"`
	TaskArn           string `json:"taskArn,omitempty" dynamodbav:"task_arn,omitempty"`
	TaskID            string `json:"taskId,omitempty" dynamodbav:"task_id,omitempty"`
	CloudWatchLogsURL string `json:"cloudWatchLogsUrl,omitempty" dynamodbav:"cloudwatch_logs_url,omitempty"`
}

type ExecutionStep struct {
	PK          string `json:"pk" dynamodbav:"pk"`
	SK          string `json:"sk" dynamodbav:"sk"`
	StepID      string `json:"stepId" dynamodbav:"step_id"`
	Sort        int    `json:"sort" dynamodbav:"sort"`
	Instruction string `json:"instruction" dynamodbav:"instruction"`
	StepType    string `json:"step_type" dynamodbav:"step_type"`
	SecretKey   string `json:"secret_key,omitempty" dynamodbav:"secret_key,omitempty"`
	// Validation step fields
	CaptureVariable    string   `json:"capture_variable,omitempty" dynamodbav:"capture_variable,omitempty"`
	ValidationType     string   `json:"validation_type,omitempty" dynamodbav:"validation_type,omitempty"`
	ValidationOperator string   `json:"validation_operator,omitempty" dynamodbav:"validation_operator,omitempty"`
	ValidationValue    string   `json:"validation_value,omitempty" dynamodbav:"validation_value,omitempty"`
	AssertionVariable  string   `json:"assertion_variable,omitempty" dynamodbav:"assertion_variable,omitempty"`
	Artefact           string   `json:"artefact" dynamodbav:"artefact"`
	Logs               []string `json:"logs" dynamodbav:"logs"`
	CreatedAt          string   `json:"createdAt" dynamodbav:"created_at"`
	ValueType          string   `json:"value_type,omitempty" dynamodbav:"value_type,omitempty"`
}

type QueueMessage struct {
	ExecutionID string `json:"execution_id"`
	UsecaseID   string `json:"usecase_id"`
}

type KeyValuePair struct {
	Key   string `json:"key"`
	Value string `json:"value"`
}

type UsecaseVariables struct {
	PK        string         `json:"pk" dynamodbav:"pk"`
	SK        string         `json:"sk" dynamodbav:"sk"`
	Variables []KeyValuePair `json:"variables" dynamodbav:"variables"`
	CreatedAt string         `json:"createdAt" dynamodbav:"created_at"`
}

type ExecutionVariables struct {
	PK        string         `json:"pk" dynamodbav:"pk"`
	SK        string         `json:"sk" dynamodbav:"sk"`
	Variables []KeyValuePair `json:"variables" dynamodbav:"variables"`
	CreatedAt string         `json:"createdAt" dynamodbav:"created_at"`
}

type SecretInfo struct {
	Key         string `json:"key"`
	SecretName  string `json:"secret_name"`
	Description string `json:"description"`
	CreatedAt   string `json:"created_at"`
}

// Request/Response types
type CreateStepRequest struct {
	UsecaseId          string `json:"usecaseId"`
	ID                 string `json:"id"`
	Sort               int    `json:"sort"`
	Instruction        string `json:"instruction"`
	StepType           string `json:"step_type"`                     // "navigation", "secret", "validation", "retrieve_value", or "assertion"
	SecretKey          string `json:"secret_key"`                    // Only for secret steps
	ValidationType     string `json:"validation_type,omitempty"`     // "bool" or "string"
	ValidationOperator string `json:"validation_operator,omitempty"` // "exact" or "contains"
	ValidationValue    string `json:"validation_value,omitempty"`    // Expected value
	CaptureVariable    string `json:"capture_variable,omitempty"`    // For retrieve_value steps
	AssertionVariable  string `json:"assertion_variable,omitempty"`  // For assertion steps
	ValueType          string `json:"value_type,omitempty"`          // For retrieve_value steps`
}

type ReorderStepsRequest struct {
	StepOrders []StepOrder `json:"step_orders"`
}

type StepOrder struct {
	StepID string `json:"step_id"`
	Sort   int    `json:"sort"`
}

type CreateUsecaseSecretsRequest struct {
	Secrets []KeyValuePair `json:"secrets"`
}

type UpdateSecretRequest struct {
	SecretKey string `json:"secret_key"`
	Value     string `json:"value"`
}

type DeleteSecretRequest struct {
	SecretKey string `json:"secret_key"`
}

type GetUsecaseSecretsResponse struct {
	Secrets []SecretInfo `json:"secrets"`
}

type CreatedByRecord struct {
	PK        string `json:"pk" dynamodbav:"pk"`
	SK        string `json:"sk" dynamodbav:"sk"`
	Email     string `json:"email" dynamodbav:"email"`
	Sub       string `json:"sub" dynamodbav:"sub"`
	CreatedAt string `json:"createdAt" dynamodbav:"createdAt"`
}

type UsecaseHeaders struct {
	PK        string            `json:"pk" dynamodbav:"pk"`
	SK        string            `json:"sk" dynamodbav:"sk"`
	Headers   map[string]string `json:"headers" dynamodbav:"headers"`
	CreatedAt string            `json:"createdAt" dynamodbav:"created_at"`
}

type ExecutionHeaders struct {
	PK        string            `json:"pk" dynamodbav:"pk"`
	SK        string            `json:"sk" dynamodbav:"sk"`
	Headers   map[string]string `json:"headers" dynamodbav:"headers"`
	CreatedAt string            `json:"createdAt" dynamodbav:"created_at"`
}

type CreateUsecaseHeadersRequest struct {
	Headers map[string]string `json:"headers"`
}

type GetUsecaseHeadersResponse struct {
	Headers map[string]string `json:"headers"`
}

type NotificationMessage struct {
	UsecaseID   string `json:"usecase_id"`
	ExecutionID string `json:"execution_id"`
}

type UsecaseSubscription struct {
	PK        string `json:"pk" dynamodbav:"pk"`
	SK        string `json:"sk" dynamodbav:"sk"`
	Email     string `json:"email" dynamodbav:"email"`
	CreatedAt string `json:"createdAt" dynamodbav:"createdAt"`
}

type SubscriptionStatusResponse struct {
	IsSubscribed bool   `json:"is_subscribed"`
	Email        string `json:"email,omitempty"`
}

// Template models
type StepTemplate struct {
	PK          string   `json:"pk" dynamodbav:"pk"` // "TEMPLATE#<template_id>"
	SK          string   `json:"sk" dynamodbav:"sk"` // "METADATA"
	ID          string   `json:"id" dynamodbav:"id"`
	Name        string   `json:"name" dynamodbav:"name"`
	Description string   `json:"description" dynamodbav:"description"`
	Category    string   `json:"category" dynamodbav:"category"`
	Tags        []string `json:"tags" dynamodbav:"tags"`
	CreatedBy   string   `json:"created_by" dynamodbav:"created_by"` // User email
	CreatedAt   string   `json:"created_at" dynamodbav:"created_at"`
	UpdatedAt   string   `json:"updated_at" dynamodbav:"updated_at"`
	Version     int      `json:"version" dynamodbav:"version"`
}

type TemplateStep struct {
	PK                 string `json:"pk" dynamodbav:"pk"` // "TEMPLATE#<template_id>"
	SK                 string `json:"sk" dynamodbav:"sk"` // "STEP#<step_id>"
	Sort               int    `json:"sort" dynamodbav:"sort"`
	ID                 string `json:"id" dynamodbav:"id"`
	Instruction        string `json:"instruction" dynamodbav:"instruction"`
	StepType           string `json:"step_type" dynamodbav:"step_type"`
	SecretKey          string `json:"secret_key,omitempty" dynamodbav:"secret_key,omitempty"`
	CaptureVariable    string `json:"capture_variable,omitempty" dynamodbav:"capture_variable,omitempty"`
	ValidationType     string `json:"validation_type,omitempty" dynamodbav:"validation_type,omitempty"`
	ValidationOperator string `json:"validation_operator,omitempty" dynamodbav:"validation_operator,omitempty"`
	ValidationValue    string `json:"validation_value,omitempty" dynamodbav:"validation_value,omitempty"`
	AssertionVariable  string `json:"assertion_variable,omitempty" dynamodbav:"assertion_variable,omitempty"`
	CreatedAt          string `json:"created_at" dynamodbav:"created_at"`
	ValueType          string `json:"value_type,omitempty" dynamodbav:"value_type,omitempty"`
}

type TemplateVariables struct {
	PK        string         `json:"pk" dynamodbav:"pk"` // "TEMPLATE#<template_id>"
	SK        string         `json:"sk" dynamodbav:"sk"` // "VARIABLES"
	Variables []KeyValuePair `json:"variables" dynamodbav:"variables"`
	CreatedAt string         `json:"created_at" dynamodbav:"created_at"`
}

// Request/Response types for templates
type CreateTemplateRequest struct {
	Name        string   `json:"name"`
	Description string   `json:"description"`
	Category    string   `json:"category"`
	Tags        []string `json:"tags"`
}

type UpdateTemplateRequest struct {
	Name        string   `json:"name"`
	Description string   `json:"description"`
	Category    string   `json:"category"`
	Tags        []string `json:"tags"`
}

type CreateTemplateStepRequest struct {
	TemplateID         string `json:"template_id"`
	Sort               int    `json:"sort"`
	Instruction        string `json:"instruction"`
	StepType           string `json:"step_type"`
	SecretKey          string `json:"secret_key,omitempty"`
	CaptureVariable    string `json:"capture_variable,omitempty"`
	ValidationType     string `json:"validation_type,omitempty"`
	ValidationOperator string `json:"validation_operator,omitempty"`
	ValidationValue    string `json:"validation_value,omitempty"`
	AssertionVariable  string `json:"assertion_variable,omitempty"`
	ValueType          string `json:"value_type,omitempty"`
}

type ImportTemplateRequest struct {
	TemplateID     string `json:"template_id"`
	InsertPosition int    `json:"insert_position"` // 0 = beginning, -1 = end, or specific position
}
