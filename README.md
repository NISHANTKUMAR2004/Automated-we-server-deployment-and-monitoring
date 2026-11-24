# Automated Server Configuration and Monitoring System

A production-style DevOps project using Puppet and Nagios Core for automated
server configuration, drift detection, recovery, and infrastructure monitoring.

## Core Technologies

- Puppet
- Nagios Core
- Docker / Docker Compose
- Linux
- AWS EC2
- FastAPI
- React
- PostgreSQL (only where required)

## Architecture

The project uses AWS EC2 instances for Puppet-managed infrastructure and
Nagios monitoring, while Docker is used for the application dashboard
and supporting services.

## Project Status

Development environment setup in progress.

## Repository Structure

- infrastructure/  - AWS and networking configuration
- puppet/          - Puppet manifests, modules and environments
- nagios/          - Nagios configuration and monitoring
- backend/         - FastAPI backend
- frontend/        - React dashboard
- docker/          - Docker-related configuration
- scripts/         - Setup, deployment and testing scripts
- docs/            - Architecture, setup and troubleshooting documentation
- tests/           - Automated and infrastructure tests
