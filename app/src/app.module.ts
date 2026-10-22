import { Module } from '@nestjs/common';
import { APP_FILTER, APP_GUARD } from '@nestjs/core';
import { AgentGateway } from './agents/agent.gateway';
import { HttpAgentGateway } from './agents/http.gateway';
import { MockAgentGateway } from './agents/mock.gateway';
import { AccessGuard } from './auth/access.guard';
import { AuthController } from './auth/auth.controller';
import { AuthService } from './auth/auth.service';
import { ErrorFilter } from './errors.filter';
import { CallReviewController } from './pages/call-review.controller';
import { ComplaintsController } from './pages/complaints.controller';
import { LiveCallController } from './pages/live-call.controller';
import { QualityController } from './pages/quality.controller';
import { SalesController } from './pages/sales.controller';
import { VoiceController } from './pages/voice.controller';
import { DeckController } from './pages/deck.controller';
import { PagesController } from './pages/pages.controller';

@Module({
  controllers: [AuthController, PagesController, DeckController, CallReviewController, ComplaintsController, LiveCallController, VoiceController, QualityController, SalesController],
  providers: [
    AuthService,
    // AGENTS_MODE=http calls the real Python agents; anything else serves the mock data.
    { provide: AgentGateway, useClass: process.env.AGENTS_MODE === 'http' ? HttpAgentGateway : MockAgentGateway },
    { provide: APP_GUARD, useClass: AccessGuard },
    { provide: APP_FILTER, useClass: ErrorFilter },
  ],
})
export class AppModule {}
