# language: en
Feature: Hello World

  Scenario: Say hello
    Given the system is running
    When I request a greeting
    Then I receive "Hello, World!"
