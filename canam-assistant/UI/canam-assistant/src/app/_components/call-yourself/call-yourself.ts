import { NgClass } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, Input, OnInit, output, signal } from '@angular/core';
import { FormGroup, FormBuilder, Validators, ReactiveFormsModule } from '@angular/forms';
import { CallYourselfStates } from '@ca/models';


@Component({
  selector: 'ca-app-call-yourself',
  standalone: true,
  imports: [ReactiveFormsModule, NgClass],
  templateUrl: './call-yourself.html',
  styleUrl: './call-yourself.scss'
})
export class CallYourself implements OnInit {
  
    @Input() buttonClass: string = '';
    @Input() modalPanelClass: string = '';
    @Input() modalContentClass: string = '';

    public onStateChange = output<CallYourselfStates>();

    public currentState = signal<CallYourselfStates>(CallYourselfStates.Initial);
    public callYourselfStates = CallYourselfStates;


    public formGroup!: FormGroup;

    constructor(
      private readonly formBuilder: FormBuilder, 
      private readonly http: HttpClient
    ) {}

    ngOnInit(): void {
      this.formGroup = this.formBuilder.group({
        phoneNumber: ['', [Validators.required, Validators.pattern(/^\+[1-9]\d{1,14}$/)]],
        name: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(100)]]
      });
    }

    public callYourself(): void { 
      this.currentState.set(this.callYourselfStates.Calling)
      const to = this.formGroup.get('phoneNumber')?.value;
      this.onStateChange.emit(CallYourselfStates.Calling);
      this.http.post('https://canam-assistant-153475391202.us-central1.run.app/make-call', { to }).subscribe({
        next: (response) => {
          console.error('Call success:', response);
          this.formGroup.reset();
          this.currentState.set(CallYourselfStates.CallSuccess);
          this.onStateChange.emit(CallYourselfStates.CallSuccess);
        },
        error: (error) => {
          console.error('Call failed:', error);
          this.currentState.set(CallYourselfStates.CallFailed);
          this.onStateChange.emit(CallYourselfStates.CallSuccess);
        }
      });
    }
}
