import { createApplication } from '@angular/platform-browser';
import { createCustomElement } from '@angular/elements';
import { CallYourself, VoiceChat } from '@ca/components';
import { appConfig } from './app/app.config';

// bootstrapApplication(App, appConfig)
//   .catch((err) => console.error(err));

createApplication(appConfig)
  .then((appRef) => {
    const callYourselfElement = createCustomElement(CallYourself, {injector: appRef.injector});
    customElements.define('ca-app-call-yourself', callYourselfElement);

    const voiceChatElement = createCustomElement(VoiceChat, {injector: appRef.injector});
    customElements.define('ca-app-voice-chat', voiceChatElement);
  })
  .catch((err) => {
    console.error(err);
  });