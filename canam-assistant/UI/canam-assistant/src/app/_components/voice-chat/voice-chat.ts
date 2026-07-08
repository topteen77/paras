import { NgClass, NgIf } from '@angular/common';
import { Component, Input } from '@angular/core';
import { Conversation } from '@elevenlabs/client';

@Component({
  selector: 'ca-app-voice-chat',
  imports: [NgClass],
  templateUrl: './voice-chat.html',
  styleUrl: './voice-chat.scss'
})
export class VoiceChat {

  @Input() buttonClass: string = '';
  public buttonText: string = 'Voice Chat';
  public conversation!: any;

  public async toggleConversation(): Promise<void> {
    try {
      if (this.conversation && this.conversation.isOpen()) {
        await this.conversation.endSession();
        this.conversation = null;

      } else {
        await navigator.mediaDevices.getUserMedia({ audio: true });
        this.conversation = await Conversation.startSession({
          agentId: 'agent_01jwr3f0vtfn6a5aja8ekdbq2c', // Replace with your agent ID
          onConnect: () => {
              console.log('Connected to voice chat');
              this.buttonText = 'End Voice Chat';
          },
          onDisconnect: () => {
              console.log('Disconnected from voice chat');
              this.conversation = null;
              this.buttonText = 'Voice Chat';
          },
          onError: (error) => {
              console.error('Error:', error);
          },
          onModeChange: (mode) => {
              console.log('Mode changed:', mode);
          },
      });
      }
      
    } catch (error) {
      console.error('Error starting voice chat:', error);
    }
  }

}
